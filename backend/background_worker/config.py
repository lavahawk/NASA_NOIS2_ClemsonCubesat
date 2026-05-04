from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field

from firms.firms_client import FirmsSource

DEFAULT_AREA = "-179.2,18.9,-66.9,71.4"
DEFAULT_SOURCES = (
    FirmsSource.VIIRS_SNPP_NRT,
    FirmsSource.VIIRS_NOAA20_NRT,
    FirmsSource.VIIRS_NOAA21_NRT,
)


@dataclass(slots=True)
class WorkerConfig:
    map_key: str
    database_dsn: str
    poll_interval_seconds: float = 300.0
    area: str = DEFAULT_AREA
    day_range: int = 1
    sources: tuple[str, ...] = field(default_factory=lambda: DEFAULT_SOURCES)
    migrations_dir: Path = Path("migrations")
    perimeter_cluster_threshold_km: float = 10.0
    perimeter_merge_threshold_km: float = 10.0
    active_fire_window_days: int = 5
    perimeter_point_buffer_meters: float = 375.0
    perimeter_smoothing_meters: float = 150.0

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        map_key = os.environ["FIRMS_MAP_KEY"]
        database_dsn = os.environ["DATABASE_DSN"]
        poll_interval = float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "300"))
        migrations_dir = Path(os.getenv("WORKER_MIGRATIONS_DIR", "migrations"))
        return cls(
            map_key=map_key,
            database_dsn=database_dsn,
            poll_interval_seconds=poll_interval,
            migrations_dir=migrations_dir,
            perimeter_cluster_threshold_km=float(
                os.getenv("WORKER_PERIMETER_CLUSTER_THRESHOLD_KM", "10.0")
            ),
            perimeter_merge_threshold_km=float(
                os.getenv("WORKER_PERIMETER_MERGE_THRESHOLD_KM", "10.0")
            ),
            active_fire_window_days=int(
                os.getenv("WORKER_ACTIVE_FIRE_WINDOW_DAYS", "5")
            ),
            perimeter_point_buffer_meters=float(
                os.getenv("WORKER_PERIMETER_POINT_BUFFER_METERS", "375.0")
            ),
            perimeter_smoothing_meters=float(
                os.getenv("WORKER_PERIMETER_SMOOTHING_METERS", "150.0")
            ),
        )
