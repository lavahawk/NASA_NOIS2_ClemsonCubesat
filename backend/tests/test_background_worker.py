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
from background_worker.perimeters import FirePerimeterGenerator, build_clusters
from background_worker import perimeters as perimeters_module
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


class FakePerimeterGenerator:
    def __init__(self, summary: dict[str, int] | None = None) -> None:
        self.summary = summary or {
            "perimeter_points_eligible": 0,
            "perimeter_clusters": 0,
            "perimeters_created": 0,
            "perimeters_updated": 0,
            "perimeters_consolidated": 0,
            "perimeter_clusters_skipped": 0,
        }
        self.calls: list[tuple[list, datetime]] = []

    def process_cycle(self, points, *, cycle_time: datetime):
        self.calls.append((list(points), cycle_time))
        return dict(self.summary)


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


class InMemoryPerimeterStore:
    def __init__(self) -> None:
        self.unlinked_keys: set[str] = set()
        self.perimeters: dict[str, set[str]] = {}
        self.merged_ids: set[str] = set()
        self.next_id = 0
        self.candidate_lookup: dict[tuple[str, ...], list[str]] = {}

    def filter_unlinked_point_keys(self, point_source_keys):
        return {key for key in point_source_keys if key in self.unlinked_keys}

    def find_merge_candidates(
        self,
        point_source_keys,
        *,
        cycle_time: datetime,
        active_fire_window_days: int,
        merge_threshold_km: float,
        point_buffer_meters: float,
        perimeter_smoothing_meters: float,
    ):
        lookup_key = tuple(sorted(point_source_keys))
        if lookup_key in self.candidate_lookup:
            return list(self.candidate_lookup[lookup_key])
        return [
            perimeter_id
            for perimeter_id, linked_points in self.perimeters.items()
            if perimeter_id not in self.merged_ids and linked_points.intersection(point_source_keys)
        ]

    def create_perimeter_from_points(
        self,
        point_source_keys,
        *,
        cycle_time: datetime,
        point_buffer_meters: float,
        perimeter_smoothing_meters: float,
    ) -> None:
        self.next_id += 1
        perimeter_id = f"perimeter-{self.next_id}"
        self.perimeters[perimeter_id] = set(point_source_keys)
        self.unlinked_keys.difference_update(point_source_keys)

    def merge_points_into_perimeter(
        self,
        perimeter_id: str,
        point_source_keys,
        *,
        cycle_time: datetime,
        point_buffer_meters: float,
        perimeter_smoothing_meters: float,
    ) -> None:
        self.perimeters[perimeter_id].update(point_source_keys)
        self.unlinked_keys.difference_update(point_source_keys)

    def consolidate_perimeters(
        self,
        perimeter_ids,
        point_source_keys,
        *,
        cycle_time: datetime,
        point_buffer_meters: float,
        perimeter_smoothing_meters: float,
    ) -> None:
        merged_points = set(point_source_keys)
        for perimeter_id in perimeter_ids:
            merged_points.update(self.perimeters[perimeter_id])
            self.merged_ids.add(perimeter_id)
        self.next_id += 1
        self.perimeters[f"perimeter-{self.next_id}"] = merged_points
        self.unlinked_keys.difference_update(point_source_keys)


class QueryCaptureCursor:
    def __init__(self, rows=None) -> None:
        self.rows = rows or []
        self.executed: list[tuple[str, tuple | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None) -> None:
        self.executed.append((sql, params))

    def fetchall(self):
        return list(self.rows)


class QueryCaptureConnection:
    def __init__(self, rows=None) -> None:
        self.cursor_instance = QueryCaptureCursor(rows=rows)
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def cursor(self):
        return self.cursor_instance

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
        worker = BackgroundWorker(
            config,
            client=client,
            writer=FakePointsWriter(),
            perimeter_generator=FakePerimeterGenerator(),
        )
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
        perimeter_generator = FakePerimeterGenerator()
        worker = BackgroundWorker(
            config,
            client=client,
            writer=writer,
            perimeter_generator=perimeter_generator,
        )
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
        self.assertEqual(len(perimeter_generator.calls), 1)
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
        worker = BackgroundWorker(
            config,
            client=client,
            writer=writer,
            perimeter_generator=FakePerimeterGenerator(),
        )
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
        worker = BackgroundWorker(
            config,
            client=client,
            writer=writer,
            perimeter_generator=FakePerimeterGenerator(),
        )
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
        worker = BackgroundWorker(
            config,
            client=client,
            writer=writer,
            perimeter_generator=FakePerimeterGenerator(),
        )
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
            perimeter_generator=FakePerimeterGenerator(),
        )

        applied = worker.startup()

        self.assertEqual(applied, ["0001_enable_extensions_and_points"])
        self.assertEqual(migration_runner.called, 1)
        self.assertEqual(client.calls, [])


class PerimeterGenerationTests(unittest.TestCase):
    def test_build_clusters_uses_deterministic_order(self) -> None:
        ingest_time = datetime(2026, 4, 16, 16, 30, tzinfo=UTC)
        points = [
            normalize_row(
                {
                    **sample_viirs_frame().iloc[0].to_dict(),
                    "latitude": 36.40,
                    "longitude": -114.80,
                    "acq_time": 930,
                },
                source="VIIRS_NOAA20_NRT",
                ingest_time=ingest_time,
            ),
            normalize_row(
                {
                    **sample_viirs_frame().iloc[0].to_dict(),
                    "latitude": 36.00,
                    "longitude": -114.95,
                    "acq_time": 900,
                },
                source="VIIRS_NOAA20_NRT",
                ingest_time=ingest_time,
            ),
        ]

        clusters = build_clusters(points, cluster_threshold_km=1.0)

        self.assertEqual(len(clusters), 2)
        self.assertLess(clusters[0].first_detection_time, clusters[1].first_detection_time)

    def test_perimeter_generation_applies_clusters_iteratively(self) -> None:
        config = WorkerConfig(
            map_key="key",
            database_dsn="postgresql://example",
        )
        store = InMemoryPerimeterStore()
        generator = FirePerimeterGenerator(config, store)
        ingest_time = datetime(2026, 4, 16, 16, 30, tzinfo=UTC)

        point_a = normalize_row(
            {
                **sample_viirs_frame().iloc[0].to_dict(),
                "latitude": 36.0000,
                "longitude": -114.9000,
                "acq_time": 900,
            },
            source="VIIRS_NOAA20_NRT",
            ingest_time=ingest_time,
        )
        point_b = normalize_row(
            {
                **sample_viirs_frame().iloc[0].to_dict(),
                "latitude": 36.0500,
                "longitude": -114.8500,
                "acq_time": 901,
            },
            source="VIIRS_NOAA20_NRT",
            ingest_time=ingest_time,
        )

        store.unlinked_keys = {point_a.source_key, point_b.source_key}
        store.candidate_lookup = {
            (point_a.source_key,): [],
            (point_b.source_key,): ["perimeter-1"],
        }
        summary = generator.process_cycle([point_a, point_b], cycle_time=ingest_time)

        self.assertEqual(summary["perimeters_created"], 1)
        self.assertEqual(summary["perimeters_updated"], 1)
        self.assertEqual(len(store.perimeters), 1)

    def test_perimeter_generation_consolidates_multiple_candidates(self) -> None:
        config = WorkerConfig(
            map_key="key",
            database_dsn="postgresql://example",
        )
        store = InMemoryPerimeterStore()
        store.perimeters = {
            "perimeter-1": {"bridge-point"},
            "perimeter-2": {"bridge-point"},
        }
        generator = FirePerimeterGenerator(config, store)
        ingest_time = datetime(2026, 4, 16, 16, 30, tzinfo=UTC)
        point = normalize_row(
            {
                **sample_viirs_frame().iloc[0].to_dict(),
                "latitude": 36.1000,
                "longitude": -114.7000,
                "acq_time": 905,
            },
            source="VIIRS_NOAA20_NRT",
            ingest_time=ingest_time,
        )
        store.unlinked_keys = {point.source_key}
        store.candidate_lookup = {
            (point.source_key,): ["perimeter-1", "perimeter-2"],
        }

        summary = generator.process_cycle([point], cycle_time=ingest_time)

        self.assertEqual(summary["perimeters_consolidated"], 1)
        self.assertTrue({"perimeter-1", "perimeter-2"}.issubset(store.merged_ids))

    def test_find_merge_candidates_uses_latest_detection_time_and_5km_geography_distance(self) -> None:
        connection = QueryCaptureConnection(rows=[("perimeter-1",), ("perimeter-2",)])
        store = perimeters_module.PostgresFirePerimeterStore(lambda: connection)
        cycle_time = datetime(2026, 4, 16, 16, 30, tzinfo=UTC)

        result = store.find_merge_candidates(
            ["point-a", "point-b"],
            cycle_time=cycle_time,
            active_fire_window_days=5,
            merge_threshold_km=5.0,
            point_buffer_meters=375.0,
            perimeter_smoothing_meters=150.0,
        )

        self.assertEqual(result, ["perimeter-1", "perimeter-2"])
        self.assertTrue(connection.closed)
        self.assertEqual(connection.rollback_count, 0)
        executed_sql, params = connection.cursor_instance.executed[0]
        self.assertIn("fp.latest_detection_time >= %s", executed_sql)
        self.assertIn("ST_DWithin(", executed_sql)
        self.assertIn("fp.geom::geography", executed_sql)
        self.assertIn("cg.geom::geography", executed_sql)
        self.assertIn("ST_ConcaveHull(", executed_sql)
        self.assertIn("ST_Buffer(", executed_sql)
        self.assertEqual(params[2], perimeters_module.CONNECTED_HULL_TARGET_PERCENT)
        self.assertEqual(params[3], 150.0)
        self.assertEqual(params[4], 150.0)
        self.assertEqual(params[6], 5000.0)


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
