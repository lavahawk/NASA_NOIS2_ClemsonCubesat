from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True, frozen=True)
class BBox:
    west: float
    south: float
    east: float
    north: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.west, self.south, self.east, self.north)

    def as_query_string(self) -> str:
        return ",".join(_format_number(value) for value in self.as_tuple())


@dataclass(slots=True, frozen=True)
class CursorBoundary:
    acquisition_time: datetime
    source_key: str


@dataclass(slots=True, frozen=True)
class PointsQuery:
    start_time: datetime
    end_time: datetime
    bbox: BBox
    filters: dict[str, object]
    cursor: CursorBoundary | None = None

    def identity_payload(self) -> dict[str, object]:
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "bbox": self.bbox.as_query_string(),
            "filters": _normalize_filter_payload(self.filters),
        }


@dataclass(slots=True, frozen=True)
class PointRecord:
    id: UUID | str
    source_key: str
    satellite: str
    version_tag: str | None
    acquisition_time: datetime
    ingest_time: datetime
    created_at: datetime
    updated_at: datetime
    latitude: float
    longitude: float
    confidence: str | None
    frp: float | None
    bright_ti4: float | None
    bright_ti5: float | None
    scan: float | None
    track: float | None
    daynight: str | None


@dataclass(slots=True, frozen=True)
class PointsPage:
    records: list[PointRecord]
    has_more: bool
    next_cursor: CursorBoundary | None


def _normalize_filter_payload(filters: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in sorted(filters.items()):
        if isinstance(value, datetime):
            normalized[key] = value.isoformat()
        elif isinstance(value, UUID):
            normalized[key] = str(value)
        else:
            normalized[key] = value
    return normalized


def _format_number(value: float) -> str:
    return format(value, "g")
