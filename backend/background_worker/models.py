from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True, frozen=True)
class NormalizedPoint:
    source_key: str
    satellite: str
    version_tag: str | None
    raw_payload: dict[str, Any]
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
