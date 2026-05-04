# Dynamic World Client Specification

## Purpose

Implement a Python client for Google Earth Engine Dynamic World V1 optimized for this access pattern:

1. Query one point by requested day with fallback controlled by `max_days_distance`.
2. Query many random longitude/latitude points in one batch.
3. For batch calls, define one batch-level requested day and derive the working date interval from that day plus `max_days_distance`.
4. Reuse collection filtering and image-selection work within a batch call.

This specification intentionally does not require callers to provide `start` and `end` interval arguments. The query date or dates are the source of truth, and the client derives the needed search interval internally.

## Dataset Facts the Client Must Respect

- Dataset: `GOOGLE/DYNAMICWORLD/V1`
- Data is stored as an Earth Engine `ImageCollection`
- Each image corresponds to a specific Sentinel-2 acquisition
- Images are scene-based and time-specific, not a continuous daily map
- Spatial resolution: 10 meters
- The `label` band is the winning land-cover class index
- The probability bands are:
  `water`, `trees`, `grass`, `flooded_vegetation`, `crops`, `shrub_and_scrub`, `built`, `bare`, `snow_and_ice`
- A requested day may have zero matching images at a given point

This means the client must not assume a valid Dynamic World image exists for every calendar day.

## Core Design

The recommended architecture is a single `DynamicWorldClient` with:

- Earth Engine initialization
- explicit credential handling
- single-point querying
- batch querying
- internal per-call grouping and image reuse
- optional small caches for repeated date-resolution work

The main optimization target is the batch method:

- normalize the batch-level requested day once
- derive a single working interval from that day
- filter the collection once for that derived interval
- resolve that requested day to one selected image
- sample all batch points together with `sampleRegions()`

This matches the expected workload better than requiring callers to manage intervals explicitly.

## High-Level Behavior

Single point:

```python
client = DynamicWorldClient(...)

result = client.get_land_cover(
    when="2024-05-04",
    longitude=-82.1234,
    latitude=34.6789,
    max_days_distance=7,
)
```

Batch:

```python
results = client.get_land_cover_batch(
    when="2024-05-04",
    requests=[
        DynamicWorldPointRequest(
            longitude=-82.12,
            latitude=34.67,
        ),
        DynamicWorldPointRequest(
            longitude=-82.13,
            latitude=34.68,
        ),
    ],
    max_days_distance=7,
)
```

## Class Taxonomy

The client must define:

```python
class DynamicWorldLabel:
    WATER = "water"
    TREES = "trees"
    GRASS = "grass"
    FLOODED_VEGETATION = "flooded_vegetation"
    CROPS = "crops"
    SHRUB_AND_SCRUB = "shrub_and_scrub"
    BUILT = "built"
    BARE = "bare"
    SNOW_AND_ICE = "snow_and_ice"

    BY_INDEX = {
        0: WATER,
        1: TREES,
        2: GRASS,
        3: FLOODED_VEGETATION,
        4: CROPS,
        5: SHRUB_AND_SCRUB,
        6: BUILT,
        7: BARE,
        8: SNOW_AND_ICE,
    }

    @classmethod
    def all(cls) -> list[str]:
        return list(cls.BY_INDEX.values())
```

```python
PROBABILITY_BANDS = DynamicWorldLabel.all()
```

## Public API

```python
class DynamicWorldClient:
    def __init__(
        self,
        *,
        credentials = None,
        project: str | None = None,
        max_metadata_cache_size: int = 32,
        default_max_days_distance: int = 7,
        retry_attempts: int = 3,
    ) -> None:
        ...

    def get_land_cover(
        self,
        *,
        when,
        longitude: float,
        latitude: float,
        max_days_distance: int | None = None,
        include_probabilities: bool = True,
        min_top1_probability: float | None = None,
    ) -> "DynamicWorldPointResult":
        ...

    def get_land_cover_batch(
        self,
        *,
        when,
        requests,
        max_days_distance: int | None = None,
        include_probabilities: bool = False,
        min_top1_probability: float | None = None,
    ) -> list["DynamicWorldPointResult"]:
        ...
```

## Request and Result Models

```python
@dataclass(frozen=True)
class DynamicWorldPointRequest:
    longitude: float
    latitude: float
```

```python
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
```

`label_name` must be `None` or one of the string constants defined on `DynamicWorldLabel`.

## Query Date Semantics

### Supported precision

The primary supported precision is day-level.

Rules:

- `when` may be `date`, `datetime`, or string
- all `when` values are normalized to a target UTC calendar day
- v1 resolves a day, not an arbitrary intra-day timestamp

For v1, if a `datetime` is supplied, only its normalized UTC day matters.

### Result interpretation

The result model does not include a separate match-type or source field.

Instead, callers must interpret the result using the existing fields:

- exact-day match: `days_from_requested == 0`
- nearest-scene fallback: `days_from_requested > 0`
- no-data result: `matched_image_date is None`

This avoids redundant state because `matched_image_date` and `days_from_requested` already encode the match outcome.

### Single-query search interval

For `get_land_cover()`, the client derives the search interval from the requested day `D` and `max_days_distance`.

Derived interval:

- start = `D - max_days_distance days`
- end = `D + max_days_distance + 1 day`

This interval is internal to the client and is not exposed in the API.

### Batch-query search interval

For `get_land_cover_batch()`, the client derives the search interval from the batch-level requested day `D` and `max_days_distance`.

Derived interval:

- start = `D - max_days_distance days`
- end = `D + max_days_distance + 1 day`

This interval must be built once per batch call and reused across the batch.

## Authentication and Initialization

Authentication must be supplied to the client by the caller or be available in the runtime environment.

The client must accept user-supplied Earth Engine authentication information through the constructor.

Recommended constructor contract:

```python
class DynamicWorldClient:
    def __init__(
        self,
        *,
        credentials = None,
        project: str | None = None,
        max_metadata_cache_size: int = 32,
        default_max_days_distance: int = 7,
        retry_attempts: int = 3,
    ) -> None:
        ...
```

Behavior rules:

- if `credentials` is provided, the client must use it when calling `ee.Initialize(...)`
- if `project` is provided, the client must pass it through to Earth Engine initialization
- if `credentials` is not provided, the client may attempt ambient/default Earth Engine authentication already present in the runtime
- the client must not start an interactive authentication flow on its own
- the client must not read undeclared environment variables internally as part of its core contract

For v1, explicit caller-supplied credentials are the preferred production path.

### Initialization behavior

The client should initialize Earth Engine lazily on first use rather than in the constructor.

Recommended logic:

1. if already initialized, do nothing
2. if `credentials` was supplied, initialize with those credentials
3. otherwise attempt default/ambient initialization
4. if initialization fails, raise a typed authentication/setup exception

## Collection Filtering and Image Selection

### Derived collection

For each call, the client should first construct a derived collection from the internally computed interval:

```python
ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterDate(start, end)
```

For batch calls, this collection must be built once and reused across the entire call rather than rebuilt per point.

### Exact-day lookup

For a requested day `D`:

- search for images in `[D, D + 1 day)`
- only use images available within the derived collection

If multiple images exist for that day, use this deterministic rule:

1. sort by `system:time_start` ascending
2. select the earliest image of the day

This rule is fixed for v1.

### Fallback lookup

If no image exists on the requested day:

1. consider only images within the derived collection
2. consider only images whose absolute day distance from `D` is `<= max_days_distance`
3. sort by:
   1. absolute day distance ascending
   2. `system:time_start` ascending
4. select the first image

This means ties prefer earlier acquisitions. That preference is intentional for v1.

### No-data condition

Return a structured no-data result when:

- there is no valid image within the allowed fallback distance, or
- the chosen image returns null/masked values at the requested point

For v1, if the selected image has a null/masked value at the point, the client should return a structured `no_data` result and should not continue searching alternate candidate images.

## Point Sampling Semantics

Once an image is selected:

- sample only the requested point
- request only `label` and the probability bands
- use 10 meter scale
- avoid broader geometry or raster export behavior

Recommended pattern:

```python
values = image.select(["label", *PROBABILITY_BANDS]).reduceRegion(
    reducer=ee.Reducer.first(),
    geometry=point,
    scale=10,
    maxPixels=1e6,
)
```

For a point query, `Reducer.first()` is sufficient.

## Batch Query Semantics

The batch method is the primary optimization path.

Recommended behavior:

1. normalize and validate the batch-level requested day
2. validate all point requests
3. derive the batch search interval from that requested day and `max_days_distance`
4. build the derived collection once
5. resolve that requested day to one selected image
6. build a `FeatureCollection` of all requested points
7. sample those points with `sampleRegions()`
8. map sampled rows back to input order

Recommended pattern:

```python
fc = ee.FeatureCollection([
    ee.Feature(ee.Geometry.Point([lon, lat]), {"request_id": request_id})
    for request_id, lon, lat in ...
])

sampled = image.select(["label", *PROBABILITY_BANDS]).sampleRegions(
    collection=fc,
    scale=10,
    geometries=False,
)
```

This is the primary performance optimization for many random points queried for the same requested day.

## Efficiency Requirements

### 1. Build the collection once per call

The implementation must avoid rebuilding the global collection query per request in a batch.

The expected efficient flow is:

1. build the derived collection once
2. resolve the requested day to one image once
3. sample all batch points against that image

### 2. Minimize `getInfo()` calls

Earth Engine round trips should be minimized.

Preferred pattern:

- keep filtering and selection server-side
- retrieve compact metadata once per call when useful
- retrieve compact sampling results once per image group

### 3. Favor batch sampling

When multiple points map to the same selected image, use `sampleRegions()` rather than repeated single-point `reduceRegion()` calls.

### 4. Keep band requests narrow

Only request:

- `label`
- the 9 probability bands

Do not fetch Sentinel-2 imagery, visualization products, or composites in the core client.

## Confidence Handling

The client must always compute:

- `label_name`
- `top1_probability`

If `include_probabilities=True`, also return the full class-probability dictionary.

If `min_top1_probability` is provided:

- return the normal result
- set `is_low_confidence=True` when `top1_probability < min_top1_probability`

For v1, the client must not replace the label with a special `uncertain` class.

## Input Validation

The client must validate:

- longitude in `[-180, 180]`
- latitude in `[-90, 90]`
- valid date/time parsing
- batch-level `when` is valid for `get_land_cover_batch()`
- batch request list is not empty
- `max_days_distance >= 0`

The client should also reject dates before the supported Dynamic World lower bound.

For v1, use:

- lower bound date: `2015-06-27`

## Error Handling

Use typed exceptions for:

- invalid coordinates
- invalid date/time input
- empty batch request list
- Earth Engine authentication/setup failures

Use structured `no_data` results instead of exceptions for:

- no image within allowed fallback distance
- null/masked sampled pixel values

Transient Earth Engine request failures may be retried with bounded retries.

## Internal Helper Methods

Recommended private methods include:

- `_initialize_ee()`
- `_normalize_day(value)`
- `_validate_coordinates(longitude, latitude)`
- `_build_point(longitude, latitude)`
- `_derive_single_interval(requested_day, max_days_distance)`
- `_derive_batch_interval(requested_day, max_days_distance)`
- `_get_collection_for_interval(start, end)`
- `_get_interval_metadata(start, end, max_days_distance)`
- `_resolve_image_for_day(requested_day, interval_metadata)`
- `_sample_point(image, point)`
- `_sample_points(image, points)`
- `_format_result(...)`

## Testing Requirements

The implementation should be covered by tests for:

1. single-query day normalization
2. batch-query day normalization
3. single-query interval derivation from requested day
4. batch-query interval derivation from batch-level requested day
5. rejection of empty batch requests
6. explicit-credentials initialization path
7. ambient/default-auth initialization path
8. authentication failure behavior
9. exact-day image selection
10. nearest-scene fallback inside the derived interval
11. no-data behavior when no image is within tolerance
12. no-data behavior for null/masked sampled pixels
13. label mapping correctness
14. low-confidence flag behavior
15. metadata cache behavior
16. batch sampling behavior using one selected image
17. result ordering preservation in batch responses

Use mocks for most unit tests and keep a separate small integration suite for real Earth Engine queries.

## Non-Goals

The first version of this client should not include:

- caller-managed time-window objects
- map visualization helpers
- raster export helpers
- polygon or regional statistics APIs
- Sentinel-2 linked imagery methods
- annual composite generation
- change-detection workflows
- eager local download of all imagery in a derived interval

## Recommended Build Order

1. Implement constants, request/result models, and exceptions.
2. Implement `DynamicWorldClient`.
3. Implement authentication and lazy Earth Engine initialization.
4. Implement day normalization and interval derivation.
5. Implement collection construction from derived intervals.
6. Implement exact-day image resolution.
7. Implement nearest-scene fallback inside the derived interval.
8. Implement single-point sampling.
9. Implement same-day batch `sampleRegions()` sampling.
10. Add optional metadata caching.
11. Add tests.

## Final Recommendation

The correct v1 architecture is a single client with day-centered queries:

- `get_land_cover()` derives its own search interval from the requested day and `max_days_distance`
- `get_land_cover_batch()` takes one batch-level requested day and derives one batch interval from it
- the client resolves that requested day against the derived interval
- and the batch method samples all batch points from the one selected image for efficient sampling

This design removes redundant interval arguments while preserving the important performance benefits for batch workloads.
