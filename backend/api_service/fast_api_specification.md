# FastAPI Specification 1.2

## Purpose

The FastAPI service is responsible for serving read-only geospatial API responses from the PostGIS data written by the background worker.

Its primary job is to query worker-managed hotspot point records from `public.points` and return them in a client-consumable format for the frontend.

This service is a separate process from the background worker. The worker is the only writer for `public.points`; the FastAPI service is read-only with respect to that table.

## Relationship To Other Backend Components

- The background worker ingests FIRMS hotspot data and stores normalized records in PostGIS.
- The FastAPI service reads those normalized records from PostGIS.
- The FastAPI service must not call the FIRMS API during normal request handling.
- The FastAPI service must not modify worker-managed hotspot rows.

This specification depends on the storage contract defined in [background-worker-specification.md](C:/Users/arche/OneDrive/Desktop/MVP/backend/background-worker-specification.md).

## Scope

This specification covers:

- read-only HTTP endpoints backed by PostGIS
- response structure for hotspot point data
- temporal and spatial query parameters
- cursor-based pagination behavior
- metadata returned alongside point results
- filtering behavior
- basic API validation and error handling

## API Versioning

The API must use a versioned prefix.

This specification defines:

- `GET /v1/points`

## Data Source

The FastAPI service reads from `public.points`, which is owned and populated by the background worker.

The relevant point attributes currently available from that table are:

- `id`
- `source_key`
- `satellite`
- `version_tag`
- `raw_payload`
- `acquisition_time`
- `ingest_time`
- `created_at`
- `updated_at`
- `latitude`
- `longitude`
- `geom`
- `confidence`
- `frp`
- `bright_ti4`
- `bright_ti5`
- `scan`
- `track`
- `daynight`

## Time Zone Policy

All request-time filtering and all response timestamps must use UTC.

- request timestamps must already be expressed in UTC
- database comparisons against `acquisition_time` and other temporal fields must use UTC
- response timestamps must be emitted as UTC ISO 8601 strings

## Time Window Contract

The API must enforce a maximum request window measured in days.

For the current MVP:

- the maximum allowed time range must be configurable through a global setting
- the default maximum must be `10` days

The API must reject requests whose `end_time - start_time` exceeds the configured maximum range.

## Response Contract

Because this API must return pagination metadata in addition to geospatial results, the top-level response body is not a raw GeoJSON `FeatureCollection`.

Instead, the API must return a JSON object that wraps a valid GeoJSON `FeatureCollection`.

### Top-Level Response Shape

```json
{
  "points": {
    "type": "FeatureCollection",
    "features": []
  },
  "next_cursor": "opaque-cursor-token",
  "has_more": true
}
```

### Response Field Rules

- `points` must be a valid GeoJSON `FeatureCollection`
- `next_cursor` must be either an opaque cursor string or `null` when there are no more results
- `has_more` must indicate whether another page is available

The API may include additional metadata fields later, but the fields above are the minimum required by this specification.

## GeoJSON Contract

The `points` field must contain a valid GeoJSON `FeatureCollection`.

### Point Feature Shape

Each hotspot row must be returned as a GeoJSON `Feature`.

Each feature must include:

- `type` with value `Feature`
- `geometry` as a GeoJSON `Point`
- `properties` containing the non-geometry hotspot attributes

Example shape:

```json
{
  "type": "Feature",
  "geometry": {
    "type": "Point",
    "coordinates": [-114.91005, 36.35788]
  },
  "properties": {
    "id": "uuid",
    "source_key": "36.35788|-114.91005|2026-03-01T09:11+00:00|VIIRS_NOAA20_NRT",
    "satellite": "VIIRS_NOAA20_NRT",
    "version_tag": "2.0NRT",
    "acquisition_time": "2026-03-01T09:11:00+00:00",
    "ingest_time": "2026-03-01T09:15:00+00:00",
    "created_at": "2026-03-01T09:15:00+00:00",
    "updated_at": "2026-03-01T09:15:00+00:00",
    "latitude": 36.35788,
    "longitude": -114.91005,
    "confidence": "n",
    "frp": 0.68,
    "bright_ti4": 304.68,
    "bright_ti5": 284.34,
    "scan": 0.39,
    "track": 0.44,
    "daynight": "N"
  }
}
```

### Geometry Rules

- `geometry.type` must be `Point`
- `geometry.coordinates` must be `[longitude, latitude]`
- geometry must reflect the stored PostGIS point in SRID 4326

### Properties Rules

At minimum, the `properties` object must include:

- `id`
- `source_key`
- `satellite`
- `version_tag`
- `acquisition_time`
- `ingest_time`
- `created_at`
- `updated_at`
- `latitude`
- `longitude`
- `confidence`
- `frp`
- `bright_ti4`
- `bright_ti5`
- `scan`
- `track`
- `daynight`

The API must not include:

- `geom` in `properties`
- `raw_payload` in `properties`

All fields that are exposed as filterable query fields must also be present in the GeoJSON feature `properties` output.

## Endpoint

### `GET /v1/points`

Returns hotspot points from `public.points` together with pagination metadata.

## Query Parameters

The endpoint must support these required parameters:

- `start_time`
- `end_time`
- `bbox`

The endpoint must also support these optional parameters:

- `cursor`
- filter parameters

## Request Parameter Contract

The `/v1/points` endpoint must use the following query parameter names.

### Required Query Parameters

- `start_time`
- `end_time`
- `bbox`

### Pagination Query Parameters

- `cursor`

### Filter Query Parameters

- `id`
- `source_key`
- `satellite`
- `version_tag`
- `ingest_time_start`
- `ingest_time_end`
- `created_at_start`
- `created_at_end`
- `updated_at_start`
- `updated_at_end`
- `confidence`
- `frp_min`
- `frp_max`
- `bright_ti4_min`
- `bright_ti4_max`
- `bright_ti5_min`
- `bright_ti5_max`
- `scan_min`
- `scan_max`
- `track_min`
- `track_max`
- `daynight`

### Parameter Validation Rules

- `start_time` and `end_time` must be valid UTC datetimes
- `start_time` must be less than or equal to `end_time`
- `bbox` must contain exactly four comma-separated numeric values
- `cursor` must be either absent or a valid server-generated cursor
- every `*_min` and `*_max` parameter must be numeric
- when both `*_min` and `*_max` are provided, `min <= max` must hold
- `id` must be a valid UUID
- `confidence`, `satellite`, `version_tag`, `source_key`, and `daynight` must be treated as exact-match strings

### Invalid Parameter Combination Rules

The API must reject requests when:

- `start_time > end_time`
- the requested time window exceeds the configured maximum
- a min/max range is inverted
- a cursor is supplied together with query parameters that do not match the original cursor-bound query
- any filter parameter is malformed, unsupported, or semantically invalid

### Required Parameters

#### `start_time`

- required
- must be a UTC datetime value
- may include second-level precision in the request
- recommended input format: ISO 8601 UTC string, for example `2026-04-16T00:00:00Z`

#### `end_time`

- required
- must be a UTC datetime value
- may include second-level precision in the request
- recommended input format: ISO 8601 UTC string, for example `2026-04-16T23:59:00Z`

#### `bbox`

- required
- must be parsed as `west,south,east,north`
- must be validated against world bounds
- must satisfy `west < east` and `south < north`
- must be applied as a spatial filter against `geom`

### Timestamp Precision Rules

The API may accept request timestamps with finer precision than one minute, but response timestamps will reflect the precision present in the stored worker data.

Because the FIRMS-derived source data is stored with minute precision, clients should expect returned hotspot timestamps to effectively have minute-level precision.

### Optional Parameters

#### `cursor`

- optional
- must be treated as an opaque server-generated token
- must not be interpreted by the client

#### Filters

The endpoint must support these filter fields and semantics:

- `id`: exact UUID match
- `source_key`: exact string match
- `acquisition_time`: bounded by `start_time` and `end_time`
- `satellite`: exact string match
- `version_tag`: exact string match
- `ingest_time_start` and `ingest_time_end`: bounded UTC datetime range for `ingest_time`
- `created_at_start` and `created_at_end`: bounded UTC datetime range for `created_at`
- `updated_at_start` and `updated_at_end`: bounded UTC datetime range for `updated_at`
- `latitude` and `longitude`: bounded by `bbox`
- `confidence`: exact string match only
- `frp`: inclusive numeric range
- `bright_ti4`: inclusive numeric range
- `bright_ti5`: inclusive numeric range
- `scan`: inclusive numeric range
- `track`: inclusive numeric range
- `daynight`: exact string match

Each supported filter must be explicitly validated.

## Database Filtering Rules

The `/v1/points` endpoint must:

1. filter on `acquisition_time` using `start_time` and `end_time`
2. filter on `geom` using the provided bounding box
3. apply any validated optional filters
4. apply cursor-based pagination using a fixed limit

Recommended time filter semantics:

- lower bound inclusive: `acquisition_time >= start_time`
- upper bound inclusive: `acquisition_time <= end_time`

Recommended spatial implementation:

- construct an envelope in SRID 4326
- apply a bounding-box or intersection filter against `geom`

## Pagination Contract

The API shall implement cursor-based pagination with a fixed global page size measured in points.

For the current MVP:

- the page size limit must default to `1000`

The API may store this value as a global constant or configuration setting, but it must not vary unpredictably across requests.

### Cursor Rules

- the cursor must be opaque to the client
- the server must generate and interpret the cursor
- the cursor must encode enough information to continue pagination consistently for the fixed API ordering
- the cursor must not require the client to understand internal field structure

For the default ordering, the cursor must be based on the ordered pair:

- `acquisition_time`
- `source_key`

The cursor must represent the last row returned on the previous page under the active query.

The cursor must also be bound to the active query shape so that it is not reused across different filters, bounding boxes, or time windows.

## Cursor Contract

The cursor must be treated as an opaque token by clients and as a validated continuation token by the server.

### Cursor Contents

At minimum, the server-side cursor payload must encode:

- the last returned row's `acquisition_time`
- the last returned row's `source_key`
- enough query identity to detect mismatches with the original request

The external cursor string may be encoded in any server-chosen format, but clients must not rely on its structure.

### Cursor Validity Rules

The cursor is valid only when all of the following match the original request used to generate it:

- `start_time`
- `end_time`
- `bbox`
- every supplied filter parameter

If any of those inputs differ, the API must reject the cursor as invalid for the current request.

### Cursor Continuation Rules

The server must resume strictly after the row identified by the cursor payload.

That means the continuation condition must be based on:

- rows with `acquisition_time` earlier than the cursor `acquisition_time`
- or rows with the same `acquisition_time` and `source_key` greater than the cursor `source_key`

### Cursor Failure Behavior

The API must reject the request with a `400 Bad Request` response when:

- the cursor cannot be decoded
- the cursor is malformed
- the cursor does not match the active request shape

### Pagination Rules

- query results must be capped at the configured page size
- `has_more` must be `true` when another page exists beyond the current response
- `next_cursor` must contain the token required to fetch the next page when `has_more=true`
- `next_cursor` must be `null` when `has_more=false`

## Ordering

The API should return rows ordered by:

1. `acquisition_time` descending
2. `source_key` ascending

This provides deterministic output and stable pagination behavior. The next page must begin strictly after the last returned row from the previous page.

That means the pagination boundary is defined by:

- rows with `acquisition_time` earlier than the cursor `acquisition_time`
- or rows with the same `acquisition_time` and `source_key` greater than the cursor `source_key`

## Error Handling

For invalid request parameters, the API must return a `400 Bad Request` response.

Examples:

- missing `start_time`
- missing `end_time`
- missing `bbox`
- invalid timestamp format
- time range exceeding the configured maximum
- invalid bbox format
- invalid cursor
- unsupported filter field or invalid filter value

Invalid filters must not be treated as empty result sets.

If any filter parameter is malformed, unsupported, or semantically invalid, the API must reject the request with a `400 Bad Request` response and return a JSON error body identifying the failing parameter and the reason.

### HTTP Status Code Contract

The API must use these status codes for the following classes of outcomes:

- `200 OK`: the request is valid and the API successfully returns a response body, including empty result sets
- `400 Bad Request`: malformed, invalid, unsupported, or inconsistent query parameters, including invalid cursors
- `404 Not Found`: unknown route
- `500 Internal Server Error`: unexpected server-side failure during request handling
- `503 Service Unavailable`: temporary database unavailability or other temporary infrastructure dependency failure, when the server can identify the condition as transient

The API should avoid leaking internal database details in error messages.

### Error Response Body

For `400` responses, the API should return a JSON error body with at least:

- `error`
- `message`

When applicable, the API should also include:

- `parameter`

Example:

```json
{
  "error": "invalid_query_parameter",
  "parameter": "frp_min",
  "message": "frp_min must be numeric"
}
```

## Performance Expectations

The initial MVP may use direct database queries without advanced caching.

The API should still:

- rely on worker-created indexes where possible
- avoid unnecessary transformation passes
- serialize directly from normalized database rows into GeoJSON
- enforce bounded page sizes to avoid oversized responses

## Out Of Scope For This Version

This specification defines only point-serving behavior.

The FastAPI service must not expose polygon endpoints under this specification unless a polygon data model, storage contract, and endpoint contract are defined separately.
