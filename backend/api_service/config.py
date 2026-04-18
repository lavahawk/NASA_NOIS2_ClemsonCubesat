from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ApiConfig:
    database_dsn: str
    page_size: int = 1000
    max_time_range_days: int = 10
    allowed_origins: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> "ApiConfig":
        return cls(
            database_dsn=os.environ["DATABASE_DSN"],
            page_size=int(os.getenv("API_PAGE_SIZE", "1000")),
            max_time_range_days=int(os.getenv("API_MAX_TIME_RANGE_DAYS", "10")),
            allowed_origins=_parse_allowed_origins(os.getenv("API_ALLOWED_ORIGINS", "[]")),
        )


def _parse_allowed_origins(value: str) -> tuple[str, ...]:
    text = value.strip()
    if not text:
        return ()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = [item.strip() for item in text.split(",") if item.strip()]

    if not isinstance(parsed, list):
        raise ValueError("API_ALLOWED_ORIGINS must be a JSON array or comma-separated list")

    origins: list[str] = []
    for item in parsed:
        if not isinstance(item, str):
            raise ValueError("API_ALLOWED_ORIGINS entries must be strings")
        origin = item.strip()
        if origin:
            origins.append(origin)
    return tuple(origins)
