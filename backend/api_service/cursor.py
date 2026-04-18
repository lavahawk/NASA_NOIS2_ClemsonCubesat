from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime

from .errors import QueryValidationError
from .models import CursorBoundary, PointsQuery


def encode_cursor(query: PointsQuery, boundary: CursorBoundary) -> str:
    # Bind the continuation token to the original query so clients cannot reuse it
    # across different time windows, bounding boxes, or filters.
    payload = {
        "acquisition_time": boundary.acquisition_time.isoformat(),
        "source_key": boundary.source_key,
        "query_hash": _query_hash(query),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(token: str, query: PointsQuery) -> CursorBoundary:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise QueryValidationError("cursor is malformed", parameter="cursor") from exc

    if not isinstance(payload, dict):
        raise QueryValidationError("cursor is malformed", parameter="cursor")

    if payload.get("query_hash") != _query_hash(query):
        raise QueryValidationError(
            "cursor does not match the active request parameters",
            parameter="cursor",
        )

    acquisition_time_text = payload.get("acquisition_time")
    source_key = payload.get("source_key")
    if not isinstance(acquisition_time_text, str) or not isinstance(source_key, str) or not source_key:
        raise QueryValidationError("cursor is malformed", parameter="cursor")

    try:
        acquisition_time = datetime.fromisoformat(acquisition_time_text)
    except ValueError as exc:
        raise QueryValidationError("cursor is malformed", parameter="cursor") from exc

    return CursorBoundary(acquisition_time=acquisition_time, source_key=source_key)


def _query_hash(query: PointsQuery) -> str:
    payload = json.dumps(query.identity_payload(), separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
