from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from typing import Any, Protocol

from .models import NormalizedPoint

INSERT_POINT_SQL = """
INSERT INTO public.points (
    source_key,
    satellite,
    version_tag,
    raw_payload,
    acquisition_time,
    ingest_time,
    created_at,
    updated_at,
    latitude,
    longitude,
    geom,
    confidence,
    frp,
    bright_ti4,
    bright_ti5,
    scan,
    track,
    daynight
)
VALUES (
    %s,
    %s,
    %s,
    %s::jsonb,
    %s,
    %s,
    %s,
    %s,
    %s,
    %s,
    ST_SetSRID(ST_MakePoint(%s, %s), 4326),
    %s,
    %s,
    %s,
    %s,
    %s,
    %s,
    %s
)
ON CONFLICT (source_key) DO NOTHING
"""


class ConnectionFactory(Protocol):
    def __call__(self) -> Any: ...


class PointsWriter:
    def insert_points(self, points: Sequence[NormalizedPoint]) -> int:
        raise NotImplementedError


class PostgresPointsWriter(PointsWriter):
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def insert_points(self, points: Sequence[NormalizedPoint]) -> int:
        if not points:
            return 0
        with _managed_connection(self._connection_factory()) as connection:
            with connection.cursor() as cursor:
                inserted = 0
                for point in points:
                    cursor.execute(INSERT_POINT_SQL, _point_params(point))
                    inserted += _rowcount_or_zero(cursor.rowcount)
            connection.commit()
        return inserted


def create_psycopg_connection_factory(dsn: str) -> ConnectionFactory:
    def factory() -> Any:
        try:
            import psycopg  # type: ignore

            return psycopg.connect(dsn)
        except ImportError:
            try:
                import psycopg2  # type: ignore

                return psycopg2.connect(dsn)
            except ImportError as exc:
                raise RuntimeError(
                    "PostgreSQL driver not installed. Install psycopg or psycopg2 to run the worker."
                ) from exc

    return factory


def _point_params(point: NormalizedPoint) -> tuple[Any, ...]:
    return (
        point.source_key,
        point.satellite,
        point.version_tag,
        json.dumps(point.raw_payload, separators=(",", ":"), default=str),
        point.acquisition_time,
        point.ingest_time,
        point.created_at,
        point.updated_at,
        point.latitude,
        point.longitude,
        point.longitude,
        point.latitude,
        point.confidence,
        point.frp,
        point.bright_ti4,
        point.bright_ti5,
        point.scan,
        point.track,
        point.daynight,
    )


def _rowcount_or_zero(rowcount: Any) -> int:
    if isinstance(rowcount, int) and rowcount > 0:
        return rowcount
    return 0


@contextmanager
def _managed_connection(connection: Any):
    try:
        yield connection
    except Exception:
        if hasattr(connection, "rollback"):
            connection.rollback()
        raise
    finally:
        if hasattr(connection, "close"):
            connection.close()
