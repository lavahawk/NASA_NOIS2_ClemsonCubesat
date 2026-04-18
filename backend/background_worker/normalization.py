from __future__ import annotations

from datetime import UTC, datetime
import math
from typing import Any

import pandas as pd

from .models import NormalizedPoint

REQUIRED_COLUMNS = {
    "latitude",
    "longitude",
    "acq_date",
    "acq_time",
}


class NormalizationError(ValueError):
    pass


def validate_frame(frame: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        missing_columns = ", ".join(sorted(missing))
        raise NormalizationError(f"missing required FIRMS columns: {missing_columns}")


def normalize_frame(
    frame: pd.DataFrame,
    *,
    source: str,
    ingest_time: datetime,
) -> list[NormalizedPoint]:
    validate_frame(frame)
    return [
        normalize_row(row, source=source, ingest_time=ingest_time)
        for row in frame.to_dict(orient="records")
    ]


def normalize_row(
    row: dict[str, Any],
    *,
    source: str,
    ingest_time: datetime,
) -> NormalizedPoint:
    latitude = round(_require_float(row.get("latitude"), "latitude"), 5)
    longitude = round(_require_float(row.get("longitude"), "longitude"), 5)
    acquisition_time = _parse_acquisition_time(row.get("acq_date"), row.get("acq_time"))
    satellite = source
    raw_payload = _normalize_payload(row)

    return NormalizedPoint(
        source_key=build_source_key(
            latitude=latitude,
            longitude=longitude,
            acquisition_time=acquisition_time,
            satellite=satellite,
        ),
        satellite=satellite,
        version_tag=_optional_text(row.get("version")),
        raw_payload=raw_payload,
        acquisition_time=acquisition_time,
        ingest_time=ingest_time,
        created_at=ingest_time,
        updated_at=ingest_time,
        latitude=latitude,
        longitude=longitude,
        confidence=_optional_text(row.get("confidence")),
        frp=_optional_float(row.get("frp")),
        bright_ti4=_optional_float(row.get("bright_ti4")),
        bright_ti5=_optional_float(row.get("bright_ti5")),
        scan=_optional_float(row.get("scan")),
        track=_optional_float(row.get("track")),
        daynight=_optional_text(row.get("daynight")),
    )


def build_source_key(
    *,
    latitude: float,
    longitude: float,
    acquisition_time: datetime,
    satellite: str,
) -> str:
    minute_precision = acquisition_time.astimezone(UTC).replace(second=0, microsecond=0)
    return (
        f"{latitude:.5f}|{longitude:.5f}|"
        f"{minute_precision.isoformat(timespec='minutes')}|{satellite}"
    )


def _parse_acquisition_time(acq_date: Any, acq_time: Any) -> datetime:
    if not isinstance(acq_date, str) or not acq_date.strip():
        raise NormalizationError("acq_date is required")

    time_text = _normalize_acq_time(acq_time)
    try:
        parsed = datetime.strptime(f"{acq_date.strip()} {time_text}", "%Y-%m-%d %H%M")
    except ValueError as exc:
        raise NormalizationError(
            f"invalid acquisition timestamp: date={acq_date!r} time={acq_time!r}"
        ) from exc
    return parsed.replace(tzinfo=UTC)


def _normalize_acq_time(value: Any) -> str:
    if value is None or _is_nan(value):
        raise NormalizationError("acq_time is required")
    if isinstance(value, str):
        compact = value.strip()
        if not compact:
            raise NormalizationError("acq_time is required")
        if ":" in compact:
            compact = compact.replace(":", "")
        if not compact.isdigit():
            raise NormalizationError(f"invalid acq_time: {value!r}")
        return compact.zfill(4)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minute_value = int(value)
        return str(minute_value).zfill(4)
    raise NormalizationError(f"invalid acq_time: {value!r}")
def _normalize_payload(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        normalized[str(key)] = _json_safe(value)
    return normalized


def _json_safe(value: Any) -> Any:
    if value is None or _is_nan(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def _optional_text(value: Any) -> str | None:
    if value is None or _is_nan(value):
        return None
    text = str(value).strip()
    return text or None


def _require_float(value: Any, field_name: str) -> float:
    converted = _optional_float(value)
    if converted is None:
        raise NormalizationError(f"{field_name} is required")
    return converted


def _optional_float(value: Any) -> float | None:
    if value is None or _is_nan(value):
        return None
    if isinstance(value, bool):
        raise NormalizationError(f"boolean value is not valid numeric data: {value!r}")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise NormalizationError(f"invalid numeric value: {value!r}") from exc


def _is_nan(value: Any) -> bool:
    return isinstance(value, float) and math.isnan(value)
