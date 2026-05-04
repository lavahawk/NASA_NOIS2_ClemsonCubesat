from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import logging
import time

import pandas as pd

from firms.firms_client import FirmsClient, FirmsError

from .config import WorkerConfig
from .migrations import MigrationRunner
from .models import NormalizedPoint
from .normalization import NormalizationError, normalize_frame
from .perimeters import FirePerimeterGenerator, PostgresFirePerimeterStore
from .storage import PointsWriter, PostgresPointsWriter, create_psycopg_connection_factory

logger = logging.getLogger(__name__)


class BackgroundWorker:
    def __init__(
        self,
        config: WorkerConfig,
        *,
        client: FirmsClient | None = None,
        writer: PointsWriter | None = None,
        migration_runner: MigrationRunner | None = None,
        perimeter_generator: FirePerimeterGenerator | None = None,
    ) -> None:
        self.config = config
        self.client = client or FirmsClient(map_key=config.map_key)
        connection_factory = create_psycopg_connection_factory(config.database_dsn)
        self.writer = writer or PostgresPointsWriter(connection_factory)
        self.migration_runner = migration_runner or MigrationRunner(
            connection_factory,
            config.migrations_dir,
        )
        self.perimeter_generator = perimeter_generator or FirePerimeterGenerator(
            config,
            PostgresFirePerimeterStore(connection_factory),
        )

    def run_forever(self) -> None:
        self.startup()
        while True:
            cycle_started = time.monotonic()
            self.run_cycle()
            elapsed = time.monotonic() - cycle_started
            sleep_seconds = max(0.0, self.config.poll_interval_seconds - elapsed)
            time.sleep(sleep_seconds)

    def startup(self) -> list[str]:
        applied = self.migration_runner.apply_pending()
        if applied:
            logger.info("Applied migrations: %s", applied)
        else:
            logger.info("No pending migrations found")
        return applied

    def run_cycle(self) -> dict[str, int]:
        ingest_time = self._utc_now().replace(second=0, microsecond=0)
        query_date = ingest_time.date()
        normalized_points: list[NormalizedPoint] = []
        malformed_sources = 0
        failed_sources = 0
        skipped_sources = 0

        try:
            available_sources = self._fetch_source_max_dates()
        except FirmsError:
            logger.exception("FIRMS data_availability query failed")
            summary = {
                "sources_total": len(self.config.sources),
                "sources_failed": len(self.config.sources),
                "sources_malformed": malformed_sources,
                "sources_skipped": skipped_sources,
                "points_seen": 0,
                "points_inserted": 0,
            }
            logger.info("Completed ingestion cycle: %s", summary)
            return summary

        for source in self.config.sources:
            max_date = available_sources.get(source)
            if max_date is None:
                skipped_sources += 1
                logger.warning(
                    "Configured source %s is not present in FIRMS data_availability(ALL); skipping area query",
                    source,
                )
                continue

            requested_date = self._resolve_query_date(
                source=source,
                current_date=query_date,
                max_date=max_date,
            )
            if requested_date is None:
                skipped_sources += 1
                continue

            try:
                frame = self.client.area(
                    source=source,
                    area=self.config.area,
                    day_range=self.config.day_range,
                    date=requested_date.isoformat(),
                )
            except FirmsError:
                failed_sources += 1
                logger.exception("FIRMS query failed for source %s", source)
                continue

            try:
                source_points = self._normalize_source_frame(
                    frame=frame,
                    source=source,
                    ingest_time=ingest_time,
                )
            except NormalizationError:
                malformed_sources += 1
                logger.exception("Malformed FIRMS data returned for source %s", source)
                continue

            normalized_points.extend(source_points)

        inserted = self.writer.insert_points(normalized_points)
        perimeter_summary = {
            "perimeter_points_eligible": 0,
            "perimeter_clusters": 0,
            "perimeters_created": 0,
            "perimeters_updated": 0,
            "perimeters_consolidated": 0,
            "perimeter_clusters_skipped": 0,
        }

        # Comment out this block to disable perimeter generation without changing point ingestion.
        if self.perimeter_generator is not None:
            perimeter_summary = self.perimeter_generator.process_cycle(
                normalized_points,
                cycle_time=ingest_time,
            )

        summary = {
            "sources_total": len(self.config.sources),
            "sources_failed": failed_sources,
            "sources_malformed": malformed_sources,
            "sources_skipped": skipped_sources,
            "points_seen": len(normalized_points),
            "points_inserted": inserted,
        }
        summary.update(perimeter_summary)
        logger.info("Completed ingestion cycle: %s", summary)
        return summary

    def _utc_now(self) -> datetime:
        return datetime.now(UTC)

    def _normalize_source_frame(
        self,
        *,
        frame: pd.DataFrame,
        source: str,
        ingest_time: datetime,
    ) -> list[NormalizedPoint]:
        try:
            return normalize_frame(frame, source=source, ingest_time=ingest_time)
        except NormalizationError:
            raise
        except Exception as exc:
            raise NormalizationError(f"unexpected normalization failure for {source}") from exc

    def _fetch_source_max_dates(self) -> dict[str, date]:
        frame = self.client.data_availability(source="ALL")
        if "data_id" not in frame.columns or "max_date" not in frame.columns:
            logger.error(
                "FIRMS data_availability(ALL) response is missing data_id or max_date; no sources will be queried"
            )
            return {}

        available_sources: dict[str, date] = {}
        for row in frame.to_dict(orient="records"):
            source = str(row.get("data_id", "")).strip()
            max_date_text = str(row.get("max_date", "")).strip()
            if not source or not max_date_text:
                continue
            try:
                available_sources[source] = date.fromisoformat(max_date_text)
            except ValueError:
                logger.error(
                    "Configured source row %s has invalid max_date %r in FIRMS data_availability(ALL)",
                    source,
                    max_date_text,
                )
        return available_sources

    def _resolve_query_date(
        self,
        *,
        source: str,
        current_date: date,
        max_date: date,
    ) -> date | None:
        previous_date = current_date - timedelta(days=1)
        if current_date <= max_date:
            return current_date
        if previous_date <= max_date:
            return previous_date
        logger.error(
            "Configured source %s has max_date %s which is older than both current UTC date %s and previous UTC date %s; skipping area query",
            source,
            max_date.isoformat(),
            current_date.isoformat(),
            previous_date.isoformat(),
        )
        return None
