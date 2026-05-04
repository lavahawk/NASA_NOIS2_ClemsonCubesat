from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DynamicWorldPointRequest:
    longitude: float
    latitude: float


@dataclass(frozen=True)
class DynamicWorldPointResult:
    longitude: float
    latitude: float
    requested_date: str
    matched_image_date: str | None
    matched_image_id: str | None
    days_from_requested: int | None
    label_index: int | None
    label_name: str | None
    top1_probability: float | None
    probabilities: dict[str, float] | None
    is_low_confidence: bool
