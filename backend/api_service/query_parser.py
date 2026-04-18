from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from .config import ApiConfig
from .cursor import decode_cursor
from .errors import QueryValidationError
from .models import BBox, PointsQuery

SUPPORTED_PARAMETERS = {
    "start_time",
    "end_time",
    "bbox",
    "cursor",
    "id",
    "source_key",
    "satellite",
    "version_tag",
    "ingest_time_start",
    "ingest_time_end",
    "created_at_start",
    "created_at_end",
    "updated_at_start",
    "updated_at_end",
    "confidence",
    "frp_min",
    "frp_max",
    "bright_ti4_min",
    "bright_ti4_max",
    "bright_ti5_min",
    "bright_ti5_max",
    "scan_min",
    "scan_max",
    "track_min",
    "track_max",
    "daynight",
}

EXACT_STRING_FILTERS = {"source_key", "satellite", "version_tag", "confidence", "daynight"}
RANGE_FILTERS = {
    "frp": ("frp_min", "frp_max"),
    "bright_ti4": ("bright_ti4_min", "bright_ti4_max"),
    "bright_ti5": ("bright_ti5_min", "bright_ti5_max"),
    "scan": ("scan_min", "scan_max"),
    "track": ("track_min", "track_max"),
}
DATETIME_RANGE_FILTERS = {
    "ingest_time": ("ingest_time_start", "ingest_time_end"),
    "created_at": ("created_at_start", "created_at_end"),
    "updated_at": ("updated_at_start", "updated_at_end"),
}


def parse_points_query(raw_query: dict[str, str], config: ApiConfig) -> PointsQuery:
    _reject_unsupported_parameters(raw_query)

    start_time = _parse_utc_datetime(raw_query.get("start_time"), parameter="start_time", required=True)
    end_time = _parse_utc_datetime(raw_query.get("end_time"), parameter="end_time", required=True)
    if start_time > end_time:
        raise QueryValidationError("start_time must be less than or equal to end_time", parameter="start_time")
    if end_time - start_time > timedelta(days=config.max_time_range_days):
        raise QueryValidationError(
            f"time window must not exceed {config.max_time_range_days} days",
            parameter="end_time",
        )

    bbox = _parse_bbox(raw_query.get("bbox"))
    filters = _parse_filters(raw_query)
    # Build the query once without a cursor so cursor validation can compare against
    # the exact request shape the client is attempting to continue.
    query = PointsQuery(
        start_time=start_time,
        end_time=end_time,
        bbox=bbox,
        filters=filters,
    )

    cursor_token = raw_query.get("cursor")
    if cursor_token:
        cursor = decode_cursor(cursor_token, query)
        return PointsQuery(
            start_time=query.start_time,
            end_time=query.end_time,
            bbox=query.bbox,
            filters=query.filters,
            cursor=cursor,
        )
    return query


def _reject_unsupported_parameters(raw_query: dict[str, str]) -> None:
    for key in raw_query:
        if key not in SUPPORTED_PARAMETERS:
            raise QueryValidationError("unsupported query parameter", parameter=key)


def _parse_filters(raw_query: dict[str, str]) -> dict[str, object]:
    filters: dict[str, object] = {}

    raw_id = raw_query.get("id")
    if raw_id is not None:
        try:
            filters["id"] = UUID(raw_id)
        except ValueError as exc:
            raise QueryValidationError("id must be a valid UUID", parameter="id") from exc

    for key in EXACT_STRING_FILTERS:
        value = raw_query.get(key)
        if value is not None:
            filters[key] = value

    for field_name, (start_key, end_key) in DATETIME_RANGE_FILTERS.items():
        start_value = raw_query.get(start_key)
        end_value = raw_query.get(end_key)
        if start_value is not None:
            filters[start_key] = _parse_utc_datetime(start_value, parameter=start_key, required=True)
        if end_value is not None:
            filters[end_key] = _parse_utc_datetime(end_value, parameter=end_key, required=True)
        if start_value is not None and end_value is not None and filters[start_key] > filters[end_key]:
            raise QueryValidationError(f"{start_key} must be less than or equal to {end_key}", parameter=start_key)

    for field_name, (min_key, max_key) in RANGE_FILTERS.items():
        min_value = raw_query.get(min_key)
        max_value = raw_query.get(max_key)
        if min_value is not None:
            filters[min_key] = _parse_float(min_value, parameter=min_key)
        if max_value is not None:
            filters[max_key] = _parse_float(max_value, parameter=max_key)
        if min_value is not None and max_value is not None and filters[min_key] > filters[max_key]:
            raise QueryValidationError(f"{min_key} must be less than or equal to {max_key}", parameter=min_key)

    return filters


def _parse_utc_datetime(value: str | None, *, parameter: str, required: bool) -> datetime:
    if value is None:
        if required:
            raise QueryValidationError(f"{parameter} is required", parameter=parameter)
        raise QueryValidationError(f"{parameter} is required", parameter=parameter)

    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise QueryValidationError(f"{parameter} must be a valid UTC datetime", parameter=parameter) from exc

    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise QueryValidationError(f"{parameter} must be expressed in UTC", parameter=parameter)
    return parsed.astimezone(UTC)


def _parse_bbox(value: str | None) -> BBox:
    if value is None:
        raise QueryValidationError("bbox is required", parameter="bbox")
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise QueryValidationError("bbox must contain exactly four comma-separated numbers", parameter="bbox")
    try:
        west, south, east, north = (float(part) for part in parts)
    except ValueError as exc:
        raise QueryValidationError("bbox must contain exactly four numeric values", parameter="bbox") from exc
    if west < -180 or east > 180 or south < -90 or north > 90:
        raise QueryValidationError("bbox is outside world bounds", parameter="bbox")
    if west >= east or south >= north:
        raise QueryValidationError("bbox must satisfy west < east and south < north", parameter="bbox")
    return BBox(west=west, south=south, east=east, north=north)


def _parse_float(value: str, *, parameter: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise QueryValidationError(f"{parameter} must be numeric", parameter=parameter) from exc
