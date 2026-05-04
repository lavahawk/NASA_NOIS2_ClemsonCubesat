from __future__ import annotations

from contextlib import suppress
import json
from typing import Any
from uuid import UUID

from .errors import DatabaseUnavailableError
from .models import CursorBoundary, PerimeterRecord, PerimetersQuery, PointRecord, PointsPage, PointsQuery

SELECT_COLUMNS = """
SELECT
    id,
    source_key,
    satellite,
    version_tag,
    acquisition_time,
    ingest_time,
    created_at,
    updated_at,
    latitude,
    longitude,
    confidence,
    frp,
    bright_ti4,
    bright_ti5,
    scan,
    track,
    daynight
FROM public.points
"""

PERIMETERS_SELECT_COLUMNS = """
SELECT
    id,
    created_at,
    updated_at,
    first_detection_time,
    latest_detection_time,
    detection_count,
    merged,
    ST_AsGeoJSON(geom)::text AS geometry
FROM public.fire_perimeters
"""


class PointsRepository:
    def fetch_points(self, query: PointsQuery, *, page_size: int) -> PointsPage:
        raise NotImplementedError


class PerimetersRepository:
    def fetch_perimeters(self, query: PerimetersQuery) -> list[PerimeterRecord]:
        raise NotImplementedError


class PostgresPointsRepository(PointsRepository):
    def __init__(self, connection_factory) -> None:
        self._connection_factory = connection_factory

    def fetch_points(self, query: PointsQuery, *, page_size: int) -> PointsPage:
        sql, params = _build_points_query_sql(query, page_size)
        connection = None
        try:
            connection = self._connection_factory()
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                columns = [column[0] for column in cursor.description]
        except Exception as exc:
            raise DatabaseUnavailableError("database query failed") from exc
        finally:
            if connection is not None:
                with suppress(Exception):
                    connection.close()

        # Fetch one extra row so the API can report whether another page exists
        # without issuing a second count query.
        records = [_row_to_record(dict(zip(columns, row, strict=False))) for row in rows[:page_size]]
        has_more = len(rows) > page_size
        next_cursor = None
        if has_more and records:
            last_record = records[-1]
            next_cursor = CursorBoundary(
                acquisition_time=last_record.acquisition_time,
                source_key=last_record.source_key,
            )
        return PointsPage(records=records, has_more=has_more, next_cursor=next_cursor)


class PostgresPerimetersRepository(PerimetersRepository):
    def __init__(self, connection_factory) -> None:
        self._connection_factory = connection_factory

    def fetch_perimeters(self, query: PerimetersQuery) -> list[PerimeterRecord]:
        sql, params = _build_perimeters_query_sql(query)
        connection = None
        try:
            connection = self._connection_factory()
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                columns = [column[0] for column in cursor.description]
        except Exception as exc:
            raise DatabaseUnavailableError("database query failed") from exc
        finally:
            if connection is not None:
                with suppress(Exception):
                    connection.close()

        return [_row_to_perimeter_record(dict(zip(columns, row, strict=False))) for row in rows]


def _build_points_query_sql(query: PointsQuery, page_size: int) -> tuple[str, list[object]]:
    clauses = [
        "acquisition_time >= %s",
        "acquisition_time <= %s",
        # Pair the cheap bbox operator with an exact intersection test so the
        # spatial filter stays correct while still using the GiST index.
        "geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)",
        "ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))",
    ]
    params: list[object] = [
        query.start_time,
        query.end_time,
        query.bbox.west,
        query.bbox.south,
        query.bbox.east,
        query.bbox.north,
        query.bbox.west,
        query.bbox.south,
        query.bbox.east,
        query.bbox.north,
    ]

    _append_filter_clauses(clauses, params, query.filters)

    if query.cursor is not None:
        # Ordering is acquisition_time DESC, source_key ASC, so continuation must
        # move to older timestamps or lexicographically later keys at the same time.
        clauses.append(
            "(acquisition_time < %s OR (acquisition_time = %s AND source_key > %s))"
        )
        params.extend(
            [
                query.cursor.acquisition_time,
                query.cursor.acquisition_time,
                query.cursor.source_key,
            ]
        )

    sql = "\n".join(
        [
            SELECT_COLUMNS,
            "WHERE " + "\n  AND ".join(clauses),
            "ORDER BY acquisition_time DESC, source_key ASC",
            "LIMIT %s",
        ]
    )
    params.append(page_size + 1)
    return sql, params


def _build_perimeters_query_sql(query: PerimetersQuery) -> tuple[str, list[object]]:
    clauses = [
        "latest_detection_time >= %s",
        "latest_detection_time <= %s",
        "merged = %s",
        "geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)",
        "ST_Intersects(geom, ST_MakeEnvelope(%s, %s, %s, %s, 4326))",
    ]
    params: list[object] = [
        query.start_time,
        query.end_time,
        query.merged,
        query.bbox.west,
        query.bbox.south,
        query.bbox.east,
        query.bbox.north,
        query.bbox.west,
        query.bbox.south,
        query.bbox.east,
        query.bbox.north,
    ]

    sql = "\n".join(
        [
            PERIMETERS_SELECT_COLUMNS,
            "WHERE " + "\n  AND ".join(clauses),
            "ORDER BY latest_detection_time DESC, id ASC",
        ]
    )
    return sql, params


def _append_filter_clauses(clauses: list[str], params: list[object], filters: dict[str, object]) -> None:
    exact_field_map = {
        "id": "id",
        "source_key": "source_key",
        "satellite": "satellite",
        "version_tag": "version_tag",
        "confidence": "confidence",
        "daynight": "daynight",
    }
    for filter_name, column_name in exact_field_map.items():
        if filter_name in filters:
            clauses.append(f"{column_name} = %s")
            params.append(filters[filter_name])

    datetime_range_map = {
        "ingest_time_start": "ingest_time >= %s",
        "ingest_time_end": "ingest_time <= %s",
        "created_at_start": "created_at >= %s",
        "created_at_end": "created_at <= %s",
        "updated_at_start": "updated_at >= %s",
        "updated_at_end": "updated_at <= %s",
    }
    for filter_name, sql in datetime_range_map.items():
        if filter_name in filters:
            clauses.append(sql)
            params.append(filters[filter_name])

    numeric_range_map = {
        "frp_min": "frp >= %s",
        "frp_max": "frp <= %s",
        "bright_ti4_min": "bright_ti4 >= %s",
        "bright_ti4_max": "bright_ti4 <= %s",
        "bright_ti5_min": "bright_ti5 >= %s",
        "bright_ti5_max": "bright_ti5 <= %s",
        "scan_min": "scan >= %s",
        "scan_max": "scan <= %s",
        "track_min": "track >= %s",
        "track_max": "track <= %s",
    }
    for filter_name, sql in numeric_range_map.items():
        if filter_name in filters:
            clauses.append(sql)
            params.append(filters[filter_name])


def _row_to_record(row: dict[str, Any]) -> PointRecord:
    identifier = row["id"]
    if isinstance(identifier, str):
        with suppress(ValueError):
            identifier = UUID(identifier)
    return PointRecord(
        id=identifier,
        source_key=row["source_key"],
        satellite=row["satellite"],
        version_tag=row["version_tag"],
        acquisition_time=row["acquisition_time"],
        ingest_time=row["ingest_time"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        latitude=float(row["latitude"]),
        longitude=float(row["longitude"]),
        confidence=row["confidence"],
        frp=_optional_float(row["frp"]),
        bright_ti4=_optional_float(row["bright_ti4"]),
        bright_ti5=_optional_float(row["bright_ti5"]),
        scan=_optional_float(row["scan"]),
        track=_optional_float(row["track"]),
        daynight=row["daynight"],
    )


def _row_to_perimeter_record(row: dict[str, Any]) -> PerimeterRecord:
    identifier = row["id"]
    if isinstance(identifier, str):
        with suppress(ValueError):
            identifier = UUID(identifier)
    return PerimeterRecord(
        id=identifier,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        first_detection_time=row["first_detection_time"],
        latest_detection_time=row["latest_detection_time"],
        detection_count=int(row["detection_count"]),
        merged=bool(row["merged"]),
        geometry=json.loads(row["geometry"]),
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
