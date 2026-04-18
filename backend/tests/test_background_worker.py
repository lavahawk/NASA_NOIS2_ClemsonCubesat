from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import shutil
import unittest
import uuid

import pandas as pd

from background_worker.config import WorkerConfig
from background_worker.migrations import MigrationRunner
from background_worker.normalization import (
    NormalizationError,
    build_source_key,
    normalize_frame,
    normalize_row,
)
from background_worker.service import BackgroundWorker


class FakeFirmsClient:
    def __init__(
        self,
        frames_by_source: dict[str, pd.DataFrame],
        available_sources: list[dict[str, str]] | None = None,
    ) -> None:
        self.frames_by_source = frames_by_source
        self.calls: list[tuple[str, str, int, str | None]] = []
        self.data_availability_calls: list[str] = []
        self.available_sources = available_sources or [
            {"data_id": source, "max_date": "2026-04-16"}
            for source in frames_by_source.keys()
        ]

    def data_availability(self, source: str = "ALL") -> pd.DataFrame:
        self.data_availability_calls.append(source)
        return pd.DataFrame(self.available_sources)

    def area(
        self,
        source: str,
        area: str,
        day_range: int,
        date: str | None = None,
    ) -> pd.DataFrame:
        self.calls.append((source, area, day_range, date))
        return self.frames_by_source[source]


class FakePointsWriter:
    def __init__(self) -> None:
        self.last_points = []

    def insert_points(self, points):
        self.last_points = list(points)
        return len(self.last_points)


class FakeMigrationRunner:
    def __init__(self, applied: list[str] | None = None) -> None:
        self.applied = applied or []
        self.called = 0

    def apply_pending(self) -> list[str]:
        self.called += 1
        return list(self.applied)


class FakeCursor:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None) -> None:
        self.connection.executed.append((sql.strip(), params))
        normalized = sql.strip().upper()
        if normalized.startswith("SELECT VERSION FROM PUBLIC.SCHEMA_MIGRATIONS"):
            self.result = [(version,) for version in self.connection.applied_versions]
        elif normalized.startswith("INSERT INTO PUBLIC.SCHEMA_MIGRATIONS"):
            self.connection.applied_versions.add(params[0])

    def fetchall(self):
        return list(self.result)


class FakeConnection:
    def __init__(self, applied_versions: set[str] | None = None) -> None:
        self.applied_versions = set(applied_versions or set())
        self.executed = []
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def close(self) -> None:
        self.closed = True


def sample_viirs_frame(satellite: str = "N20") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "latitude": 36.357879,
                "longitude": -114.910051,
                "bright_ti4": 304.68,
                "scan": 0.39,
                "track": 0.44,
                "acq_date": "2026-03-01",
                "acq_time": 911,
                "satellite": satellite,
                "instrument": "VIIRS",
                "confidence": "n",
                "version": "2.0NRT",
                "bright_ti5": 284.34,
                "frp": 0.68,
                "daynight": "N",
            }
        ]
    )


class NormalizationTests(unittest.TestCase):
    def test_normalize_row_uses_query_source_for_satellite_and_source_key(self) -> None:
        ingest_time = datetime(2026, 4, 16, 16, 30, tzinfo=UTC)
        point = normalize_row(
            sample_viirs_frame().iloc[0].to_dict(),
            source="VIIRS_NOAA20_NRT",
            ingest_time=ingest_time,
        )

        self.assertEqual(point.satellite, "VIIRS_NOAA20_NRT")
        self.assertEqual(point.latitude, 36.35788)
        self.assertEqual(point.longitude, -114.91005)
        self.assertEqual(
            point.acquisition_time,
            datetime(2026, 3, 1, 9, 11, tzinfo=UTC),
        )
        self.assertEqual(
            point.source_key,
            "36.35788|-114.91005|2026-03-01T09:11+00:00|VIIRS_NOAA20_NRT",
        )

    def test_build_source_key_uses_minute_precision(self) -> None:
        key = build_source_key(
            latitude=1.23456,
            longitude=-2.34567,
            acquisition_time=datetime(2026, 3, 1, 9, 11, 52, tzinfo=UTC),
            satellite="VIIRS_SNPP_NRT",
        )
        self.assertEqual(key, "1.23456|-2.34567|2026-03-01T09:11+00:00|VIIRS_SNPP_NRT")

    def test_normalize_frame_requires_viirs_columns(self) -> None:
        ingest_time = datetime(2026, 4, 16, 16, 30, tzinfo=UTC)
        frame = pd.DataFrame([{"latitude": 1.0}])
        with self.assertRaises(NormalizationError):
            normalize_frame(frame, source="VIIRS_SNPP_NRT", ingest_time=ingest_time)


class WorkerCycleTests(unittest.TestCase):
    def _build_worker(
        self,
        client: FakeFirmsClient,
        *,
        now: datetime = datetime(2026, 4, 16, 16, 30, tzinfo=UTC),
    ) -> BackgroundWorker:
        config = WorkerConfig(
            map_key="key",
            database_dsn="postgresql://example",
        )
        worker = BackgroundWorker(config, client=client, writer=FakePointsWriter())
        worker._utc_now = lambda: now  # type: ignore[method-assign]
        return worker

    def test_worker_cycle_queries_required_sources_and_writes_points(self) -> None:
        config = WorkerConfig(map_key="key", database_dsn="postgresql://example")
        frames_by_source = {
            source: sample_viirs_frame("N" if source == "VIIRS_SNPP_NRT" else source.split("_")[1].replace("NOAA", "N"))
            for source in config.sources
        }
        client = FakeFirmsClient(frames_by_source)
        writer = FakePointsWriter()
        worker = BackgroundWorker(config, client=client, writer=writer)
        worker._utc_now = lambda: datetime(2026, 4, 16, 16, 30, tzinfo=UTC)  # type: ignore[method-assign]

        summary = worker.run_cycle()

        self.assertEqual(client.data_availability_calls, ["ALL"])
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(
            {date for _, _, _, date in client.calls},
            {"2026-04-16"},
        )
        self.assertEqual(summary["sources_total"], 3)
        self.assertEqual(summary["sources_failed"], 0)
        self.assertEqual(summary["sources_malformed"], 0)
        self.assertEqual(summary["sources_skipped"], 0)
        self.assertEqual(summary["points_seen"], 3)
        self.assertEqual(summary["points_inserted"], 3)
        self.assertEqual(len(writer.last_points), 3)
        self.assertEqual(
            {point.satellite for point in writer.last_points},
            set(config.sources),
        )

    def test_worker_cycle_skips_sources_missing_from_data_availability(self) -> None:
        config = WorkerConfig(
            map_key="key",
            database_dsn="postgresql://example",
        )
        frames_by_source = {source: sample_viirs_frame() for source in config.sources}
        client = FakeFirmsClient(
            frames_by_source,
            available_sources=[
                {"data_id": "VIIRS_SNPP_NRT", "max_date": "2026-04-16"},
                {"data_id": "VIIRS_NOAA20_NRT", "max_date": "2026-04-16"},
            ],
        )
        writer = FakePointsWriter()
        worker = BackgroundWorker(config, client=client, writer=writer)
        worker._utc_now = lambda: datetime(2026, 4, 16, 16, 30, tzinfo=UTC)  # type: ignore[method-assign]

        summary = worker.run_cycle()

        self.assertEqual(client.data_availability_calls, ["ALL"])
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(summary["sources_total"], 3)
        self.assertEqual(summary["sources_failed"], 0)
        self.assertEqual(summary["sources_malformed"], 0)
        self.assertEqual(summary["sources_skipped"], 1)
        self.assertEqual(summary["points_seen"], 2)
        self.assertEqual(summary["points_inserted"], 2)
        self.assertEqual(
            {source for source, _, _, _ in client.calls},
            {"VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT"},
        )

    def test_worker_cycle_uses_previous_day_when_current_day_is_unavailable(self) -> None:
        config = WorkerConfig(
            map_key="key",
            database_dsn="postgresql://example",
        )
        frames_by_source = {source: sample_viirs_frame() for source in config.sources}
        client = FakeFirmsClient(frames_by_source)
        writer = FakePointsWriter()
        worker = BackgroundWorker(config, client=client, writer=writer)
        worker._utc_now = lambda: datetime(2026, 4, 17, 0, 44, tzinfo=UTC)  # type: ignore[method-assign]

        summary = worker.run_cycle()

        self.assertEqual(client.data_availability_calls, ["ALL"])
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(
            {date for _, _, _, date in client.calls},
            {"2026-04-16"},
        )
        self.assertEqual(summary["sources_total"], 3)
        self.assertEqual(summary["sources_failed"], 0)
        self.assertEqual(summary["sources_malformed"], 0)
        self.assertEqual(summary["sources_skipped"], 0)
        self.assertEqual(summary["points_seen"], 3)
        self.assertEqual(summary["points_inserted"], 3)

    def test_worker_cycle_skips_sources_when_neither_current_nor_previous_day_is_available(self) -> None:
        config = WorkerConfig(
            map_key="key",
            database_dsn="postgresql://example",
        )
        frames_by_source = {source: sample_viirs_frame() for source in config.sources}
        client = FakeFirmsClient(
            frames_by_source,
            available_sources=[
                {"data_id": "VIIRS_SNPP_NRT", "max_date": "2026-04-15"},
                {"data_id": "VIIRS_NOAA20_NRT", "max_date": "2026-04-15"},
                {"data_id": "VIIRS_NOAA21_NRT", "max_date": "2026-04-15"},
            ],
        )
        writer = FakePointsWriter()
        worker = BackgroundWorker(config, client=client, writer=writer)
        worker._utc_now = lambda: datetime(2026, 4, 17, 0, 44, tzinfo=UTC)  # type: ignore[method-assign]

        summary = worker.run_cycle()

        self.assertEqual(client.data_availability_calls, ["ALL"])
        self.assertEqual(client.calls, [])
        self.assertEqual(summary["sources_total"], 3)
        self.assertEqual(summary["sources_failed"], 0)
        self.assertEqual(summary["sources_malformed"], 0)
        self.assertEqual(summary["sources_skipped"], 3)
        self.assertEqual(summary["points_seen"], 0)
        self.assertEqual(summary["points_inserted"], 0)

    def test_worker_startup_runs_migrations_before_polling(self) -> None:
        config = WorkerConfig(map_key="key", database_dsn="postgresql://example")
        client = FakeFirmsClient({source: sample_viirs_frame() for source in config.sources})
        writer = FakePointsWriter()
        migration_runner = FakeMigrationRunner(["0001_enable_extensions_and_points"])

        worker = BackgroundWorker(
            config,
            client=client,
            writer=writer,
            migration_runner=migration_runner,
        )

        applied = worker.startup()

        self.assertEqual(applied, ["0001_enable_extensions_and_points"])
        self.assertEqual(migration_runner.called, 1)
        self.assertEqual(client.calls, [])


class MigrationRunnerTests(unittest.TestCase):
    def test_apply_pending_runs_unapplied_sql_files(self) -> None:
        migrations_dir = Path("tests_runtime_migrations") / str(uuid.uuid4())
        migrations_dir.mkdir(parents=True, exist_ok=False)
        try:
            (migrations_dir / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")
            (migrations_dir / "0002_second.sql").write_text("SELECT 2;", encoding="utf-8")

            connection = FakeConnection(applied_versions={"0001_first"})
            runner = MigrationRunner(lambda: connection, migrations_dir)

            applied = runner.apply_pending()

            self.assertEqual(applied, ["0002_second"])
            executed_sql = [sql for sql, _ in connection.executed]
            self.assertTrue(any("CREATE TABLE IF NOT EXISTS public.schema_migrations" in sql for sql in executed_sql))
            self.assertTrue(any(sql == "SELECT 2;" for sql in executed_sql))
            self.assertEqual(connection.commit_count, 1)
            self.assertTrue(connection.closed)
        finally:
            shutil.rmtree(migrations_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
