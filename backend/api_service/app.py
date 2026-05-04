from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from background_worker.storage import create_psycopg_connection_factory

from .config import ApiConfig
from .cursor import encode_cursor
from .errors import DatabaseUnavailableError, QueryValidationError
from .models import PerimeterRecord, PointRecord
from .query_parser import parse_perimeters_query, parse_points_query
from .repository import (
    PerimetersRepository,
    PointsRepository,
    PostgresPerimetersRepository,
    PostgresPointsRepository,
)


def create_app(
    config: ApiConfig | None = None,
    *,
    repository: PointsRepository | None = None,
    perimeters_repository: PerimetersRepository | None = None,
) -> FastAPI:
    config = config or ApiConfig.from_env()
    repository = repository or PostgresPointsRepository(create_psycopg_connection_factory(config.database_dsn))
    perimeters_repository = perimeters_repository or PostgresPerimetersRepository(
        create_psycopg_connection_factory(config.database_dsn)
    )

    app = FastAPI()
    app.state.api_config = config
    app.state.points_repository = repository
    app.state.perimeters_repository = perimeters_repository

    if config.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(config.allowed_origins),
            allow_credentials=True,
            allow_methods=["GET", "OPTIONS"],
            allow_headers=["*"],
        )

    @app.exception_handler(QueryValidationError)
    async def handle_query_validation_error(_: Request, exc: QueryValidationError) -> JSONResponse:
        body: dict[str, Any] = {
            "error": "invalid_query_parameter",
            "message": exc.message,
        }
        if exc.parameter is not None:
            body["parameter"] = exc.parameter
        return JSONResponse(status_code=400, content=body)

    @app.exception_handler(DatabaseUnavailableError)
    async def handle_database_unavailable(_: Request, exc: DatabaseUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "error": "service_unavailable",
                "message": str(exc) or "database unavailable",
            },
        )

    @app.get("/v1/points")
    async def get_points(request: Request) -> dict[str, Any]:
        raw_query = dict(request.query_params.multi_items())
        query = parse_points_query(raw_query, config)
        page = repository.fetch_points(query, page_size=config.page_size)

        next_cursor = None
        if page.has_more and page.next_cursor is not None:
            next_cursor = encode_cursor(query, page.next_cursor)

        return {
            "points": {
                "type": "FeatureCollection",
                "features": [_record_to_feature(record) for record in page.records],
            },
            "next_cursor": next_cursor,
            "has_more": page.has_more,
        }

    @app.get("/v1/perimeters")
    async def get_perimeters(request: Request) -> dict[str, Any]:
        raw_query = dict(request.query_params.multi_items())
        query = parse_perimeters_query(raw_query, config)
        records = perimeters_repository.fetch_perimeters(query)

        return {
            "type": "FeatureCollection",
            "features": [_perimeter_to_feature(record) for record in records],
        }

    return app


def _record_to_feature(record: PointRecord) -> dict[str, Any]:
    # Emit the DB row as GeoJSON while keeping all filterable attributes in
    # properties and excluding internal storage-only fields such as raw_payload.
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [record.longitude, record.latitude],
        },
        "properties": {
            "id": str(record.id),
            "source_key": record.source_key,
            "satellite": record.satellite,
            "version_tag": record.version_tag,
            "acquisition_time": _to_utc_iso(record.acquisition_time),
            "ingest_time": _to_utc_iso(record.ingest_time),
            "created_at": _to_utc_iso(record.created_at),
            "updated_at": _to_utc_iso(record.updated_at),
            "latitude": record.latitude,
            "longitude": record.longitude,
            "confidence": record.confidence,
            "frp": record.frp,
            "bright_ti4": record.bright_ti4,
            "bright_ti5": record.bright_ti5,
            "scan": record.scan,
            "track": record.track,
            "daynight": record.daynight,
        },
    }


def _to_utc_iso(value: datetime) -> str:
    return value.isoformat()


def _perimeter_to_feature(record: PerimeterRecord) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": record.geometry,
        "properties": {
            "id": str(record.id),
            "created_at": _to_utc_iso(record.created_at),
            "updated_at": _to_utc_iso(record.updated_at),
            "first_detection_time": _to_utc_iso(record.first_detection_time),
            "latest_detection_time": _to_utc_iso(record.latest_detection_time),
            "detection_count": record.detection_count,
            "merged": record.merged,
        },
    }
