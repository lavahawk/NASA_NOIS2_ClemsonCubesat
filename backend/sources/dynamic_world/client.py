from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable

from .constants import (
    DATASET_ID,
    LOWER_BOUND_DATE,
    PROBABILITY_BANDS,
    DynamicWorldLabel,
)
from .exceptions import (
    DynamicWorldAuthenticationError,
    DynamicWorldEmptyBatchError,
    DynamicWorldInvalidCoordinatesError,
    DynamicWorldInvalidDateError,
)
from .models import DynamicWorldPointRequest, DynamicWorldPointResult

try:
    import ee  # type: ignore
except ImportError:  # pragma: no cover - exercised via initialization failure paths
    ee = None  # type: ignore


class DynamicWorldClient:
    def __init__(
        self,
        *,
        credentials: Any = None,
        project: str | None = None,
        max_metadata_cache_size: int = 32,
        default_max_days_distance: int = 7,
        retry_attempts: int = 3,
    ) -> None:
        if max_metadata_cache_size < 0:
            raise ValueError("max_metadata_cache_size must be >= 0")
        if default_max_days_distance < 0:
            raise ValueError("default_max_days_distance must be >= 0")
        if retry_attempts < 1:
            raise ValueError("retry_attempts must be >= 1")

        self._credentials = credentials
        self._project = project
        self._max_metadata_cache_size = max_metadata_cache_size
        self._default_max_days_distance = default_max_days_distance
        self._retry_attempts = retry_attempts
        self._initialized = False
        self._metadata_cache: OrderedDict[tuple[str, str], list[dict[str, Any]]] = (
            OrderedDict()
        )

    def get_land_cover(
        self,
        *,
        when: Any,
        longitude: float,
        latitude: float,
        max_days_distance: int | None = None,
        include_probabilities: bool = True,
        min_top1_probability: float | None = None,
    ) -> DynamicWorldPointResult:
        self._initialize_ee()
        requested_day = self._normalize_day(when)
        self._validate_coordinates(longitude, latitude)
        max_distance = self._resolve_max_days_distance(max_days_distance)
        point = self._build_point(longitude, latitude)
        start, end = self._derive_single_interval(requested_day, max_distance)
        collection = self._get_collection_for_interval(start, end, geometry=point)
        metadata = self._get_interval_metadata(start, end, collection)
        selected = self._resolve_image_for_day(requested_day, metadata, max_distance)
        if selected is None:
            return self._format_no_data_result(
                longitude=longitude,
                latitude=latitude,
                requested_day=requested_day,
            )

        image = self._get_image_from_collection(collection, selected["system_index"])
        sampled = self._sample_point(image, point)
        return self._format_result(
            longitude=longitude,
            latitude=latitude,
            requested_day=requested_day,
            selected_metadata=selected,
            sampled_values=sampled,
            include_probabilities=include_probabilities,
            min_top1_probability=min_top1_probability,
        )

    def get_land_cover_batch(
        self,
        *,
        when: Any,
        requests: list[DynamicWorldPointRequest],
        max_days_distance: int | None = None,
        include_probabilities: bool = False,
        min_top1_probability: float | None = None,
    ) -> list[DynamicWorldPointResult]:
        self._initialize_ee()
        requested_day = self._normalize_day(when)
        if not requests:
            raise DynamicWorldEmptyBatchError("requests must not be empty")
        for request in requests:
            self._validate_coordinates(request.longitude, request.latitude)

        max_distance = self._resolve_max_days_distance(max_days_distance)
        start, end = self._derive_batch_interval(requested_day, max_distance)
        collection = self._get_collection_for_interval(start, end)
        metadata = self._get_interval_metadata(start, end, collection)
        selected = self._resolve_image_for_day(requested_day, metadata, max_distance)
        if selected is None:
            return [
                self._format_no_data_result(
                    longitude=request.longitude,
                    latitude=request.latitude,
                    requested_day=requested_day,
                )
                for request in requests
            ]

        image = self._get_image_from_collection(collection, selected["system_index"])
        sampled_rows = self._sample_points(image, requests)
        sampled_by_id = {row["request_id"]: row for row in sampled_rows}

        results: list[DynamicWorldPointResult] = []
        for request_id, request in enumerate(requests):
            results.append(
                self._format_result(
                    longitude=request.longitude,
                    latitude=request.latitude,
                    requested_day=requested_day,
                    selected_metadata=selected,
                    sampled_values=sampled_by_id.get(request_id),
                    include_probabilities=include_probabilities,
                    min_top1_probability=min_top1_probability,
                )
            )
        return results

    def _initialize_ee(self) -> None:
        if self._initialized:
            return
        if ee is None:
            raise DynamicWorldAuthenticationError(
                "The earthengine-api package is not installed."
            )

        try:
            kwargs: dict[str, Any] = {}
            if self._credentials is not None:
                kwargs["credentials"] = self._credentials
            if self._project is not None:
                kwargs["project"] = self._project
            ee.Initialize(**kwargs)
        except Exception as exc:  # pragma: no cover - exact errors depend on ee runtime
            raise DynamicWorldAuthenticationError(
                "Failed to initialize Google Earth Engine."
            ) from exc

        self._initialized = True

    def _normalize_day(self, value: Any) -> date:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                normalized = value.replace(tzinfo=timezone.utc)
            else:
                normalized = value.astimezone(timezone.utc)
            day = normalized.date()
        elif isinstance(value, date):
            day = value
        elif isinstance(value, str):
            day = self._parse_date_string(value)
        else:
            raise DynamicWorldInvalidDateError("Unsupported date/time value type")

        if day < LOWER_BOUND_DATE:
            raise DynamicWorldInvalidDateError(
                f"Dynamic World does not support dates before {LOWER_BOUND_DATE.isoformat()}."
            )
        return day

    def _parse_date_string(self, value: str) -> date:
        raw_value = value.strip()
        if not raw_value:
            raise DynamicWorldInvalidDateError("Date string must not be empty")

        try:
            if len(raw_value) == 10:
                return date.fromisoformat(raw_value)
            normalized = raw_value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
            return parsed.date()
        except ValueError as exc:
            raise DynamicWorldInvalidDateError(
                f"Invalid date/time value: {value!r}"
            ) from exc

    def _validate_coordinates(self, longitude: float, latitude: float) -> None:
        if not (-180.0 <= longitude <= 180.0):
            raise DynamicWorldInvalidCoordinatesError(
                f"longitude must be in [-180, 180], got {longitude}"
            )
        if not (-90.0 <= latitude <= 90.0):
            raise DynamicWorldInvalidCoordinatesError(
                f"latitude must be in [-90, 90], got {latitude}"
            )

    def _build_point(self, longitude: float, latitude: float) -> Any:
        return ee.Geometry.Point([longitude, latitude])

    def _resolve_max_days_distance(self, value: int | None) -> int:
        resolved = self._default_max_days_distance if value is None else value
        if resolved < 0:
            raise ValueError("max_days_distance must be >= 0")
        return resolved

    def _derive_single_interval(
        self, requested_day: date, max_days_distance: int
    ) -> tuple[date, date]:
        return self._derive_day_centered_interval(requested_day, max_days_distance)

    def _derive_batch_interval(
        self, requested_day: date, max_days_distance: int
    ) -> tuple[date, date]:
        return self._derive_day_centered_interval(requested_day, max_days_distance)

    def _derive_day_centered_interval(
        self, requested_day: date, max_days_distance: int
    ) -> tuple[date, date]:
        start = requested_day - timedelta(days=max_days_distance)
        end = requested_day + timedelta(days=max_days_distance + 1)
        return start, end

    def _get_collection_for_interval(
        self, start: date, end: date, geometry: Any | None = None
    ) -> Any:
        collection = ee.ImageCollection(DATASET_ID).filterDate(
            start.isoformat(), end.isoformat()
        )
        if geometry is not None:
            collection = collection.filterBounds(geometry)
        return collection

    def _get_interval_metadata(
        self, start: date, end: date, collection: Any
    ) -> list[dict[str, Any]]:
        cache_key = (start.isoformat(), end.isoformat())
        if cache_key in self._metadata_cache:
            self._metadata_cache.move_to_end(cache_key)
            return self._metadata_cache[cache_key]

        metadata = self._fetch_interval_metadata(collection)
        self._metadata_cache[cache_key] = metadata
        if self._max_metadata_cache_size == 0:
            self._metadata_cache.clear()
        elif len(self._metadata_cache) > self._max_metadata_cache_size:
            self._metadata_cache.popitem(last=False)
        return metadata

    def _fetch_interval_metadata(self, collection: Any) -> list[dict[str, Any]]:
        sorted_collection = collection.sort("system:time_start")
        payload = ee.Dictionary(
            {
                "time_start": sorted_collection.aggregate_array("system:time_start"),
                "system_index": sorted_collection.aggregate_array("system:index"),
                "system_id": sorted_collection.aggregate_array("system:id"),
            }
        )
        info = self._execute_with_retries(payload.getInfo)
        times = info.get("time_start", [])
        indices = info.get("system_index", [])
        ids = info.get("system_id", [])

        metadata: list[dict[str, Any]] = []
        for time_start, system_index, system_id in zip(times, indices, ids):
            if time_start is None or system_index is None:
                continue
            image_datetime = datetime.fromtimestamp(
                float(time_start) / 1000.0, tz=timezone.utc
            )
            metadata.append(
                {
                    "system_index": system_index,
                    "system_id": system_id,
                    "time_start": int(time_start),
                    "date": image_datetime.date(),
                    "date_str": image_datetime.date().isoformat(),
                }
            )
        return metadata

    def _resolve_image_for_day(
        self,
        requested_day: date,
        interval_metadata: list[dict[str, Any]],
        max_days_distance: int,
    ) -> dict[str, Any] | None:
        if not interval_metadata:
            return None

        exact_matches = [
            item for item in interval_metadata if item["date"] == requested_day
        ]
        if exact_matches:
            return exact_matches[0]

        fallback_matches = []
        for item in interval_metadata:
            distance = abs((item["date"] - requested_day).days)
            if distance <= max_days_distance:
                fallback_matches.append((distance, item["time_start"], item))

        if not fallback_matches:
            return None

        fallback_matches.sort(key=lambda value: (value[0], value[1]))
        return fallback_matches[0][2]

    def _get_image_from_collection(self, collection: Any, system_index: str) -> Any:
        return ee.Image(
            collection.filter(ee.Filter.eq("system:index", system_index)).first()
        )

    def _sample_point(self, image: Any, point: Any) -> dict[str, Any] | None:
        selection = image.select(["label", *PROBABILITY_BANDS]).reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=point,
            scale=10,
            maxPixels=1_000_000,
        )
        values = self._execute_with_retries(selection.getInfo)
        if not values or values.get("label") is None:
            return None
        return values

    def _sample_points(
        self, image: Any, requests: list[DynamicWorldPointRequest]
    ) -> list[dict[str, Any]]:
        features = [
            ee.Feature(
                ee.Geometry.Point([request.longitude, request.latitude]),
                {"request_id": request_id},
            )
            for request_id, request in enumerate(requests)
        ]
        sample = image.select(["label", *PROBABILITY_BANDS]).sampleRegions(
            collection=ee.FeatureCollection(features),
            scale=10,
            geometries=False,
        )
        payload = self._execute_with_retries(sample.getInfo)
        results: list[dict[str, Any]] = []
        for feature in payload.get("features", []):
            properties = feature.get("properties", {})
            if properties.get("label") is None:
                continue
            results.append(properties)
        return results

    def _format_result(
        self,
        *,
        longitude: float,
        latitude: float,
        requested_day: date,
        selected_metadata: dict[str, Any],
        sampled_values: dict[str, Any] | None,
        include_probabilities: bool,
        min_top1_probability: float | None,
    ) -> DynamicWorldPointResult:
        if sampled_values is None:
            return self._format_no_data_result(
                longitude=longitude,
                latitude=latitude,
                requested_day=requested_day,
            )

        label_index = int(sampled_values["label"])
        label_name = DynamicWorldLabel.BY_INDEX.get(label_index)
        probabilities = {
            band: float(sampled_values[band])
            for band in PROBABILITY_BANDS
            if sampled_values.get(band) is not None
        }
        top1_probability = (
            probabilities.get(label_name)
            if label_name is not None
            else max(probabilities.values(), default=None)
        )
        is_low_confidence = (
            top1_probability is not None
            and min_top1_probability is not None
            and top1_probability < min_top1_probability
        )
        return DynamicWorldPointResult(
            longitude=longitude,
            latitude=latitude,
            requested_date=requested_day.isoformat(),
            matched_image_date=selected_metadata["date_str"],
            matched_image_id=selected_metadata.get("system_id")
            or selected_metadata["system_index"],
            days_from_requested=abs((selected_metadata["date"] - requested_day).days),
            label_index=label_index,
            label_name=label_name,
            top1_probability=top1_probability,
            probabilities=probabilities if include_probabilities else None,
            is_low_confidence=is_low_confidence,
        )

    def _format_no_data_result(
        self, *, longitude: float, latitude: float, requested_day: date
    ) -> DynamicWorldPointResult:
        return DynamicWorldPointResult(
            longitude=longitude,
            latitude=latitude,
            requested_date=requested_day.isoformat(),
            matched_image_date=None,
            matched_image_id=None,
            days_from_requested=None,
            label_index=None,
            label_name=None,
            top1_probability=None,
            probabilities=None,
            is_low_confidence=False,
        )

    def _execute_with_retries(self, fn: Callable[[], Any]) -> Any:
        last_error: Exception | None = None
        for _ in range(self._retry_attempts):
            try:
                return fn()
            except Exception as exc:  # pragma: no cover - retry path depends on ee runtime
                last_error = exc
        assert last_error is not None
        raise last_error


def normalize_day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)
