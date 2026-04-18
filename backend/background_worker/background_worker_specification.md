# Background Worker Specification 2.2

## Purpose

The background worker is responsible for compute-heavy and time-consuming backend tasks related to VIIRS hotspot ingestion. Its primary job is to query the NASA FIRMS API through `firms/firms_client.py`, normalize the returned hotspot records, and store them in PostGIS for retrieval by a separate FastAPI process.

## Scope

This specification covers:

- scheduled ingestion of recent VIIRS detections
- normalization of FIRMS hotspot records into a database-ready shape
- deduplication of repeated detections across polling cycles
- persistence of normalized records into PostGIS
- database migrations required by the worker schema

This specification does not cover:

- downstream API response shapes
- clustering or aggregation logic
- alerting or notification behavior
- archival or record expiration workflows

## External Dependency

The worker must use the FIRMS client defined in [firms_client_specification.md](/C:/Users/arche/OneDrive/Desktop/backend/firms/firms_client_specification.md).

The ingestion flow is expected to call `FirmsClient.area(...)`.
Each polling cycle is also expected to call `FirmsClient.data_availability(source="ALL")` before issuing any `area(...)` requests.

## Worker Responsibilities

The worker must:

1. Poll the FIRMS API on a rolling cadence of approximately every 5 minutes.
2. Query FIRMS source availability before requesting hotspot data.
3. Query the latest available 24-hour VIIRS detections for the North America bounding box.
4. Normalize FIRMS rows into a consistent internal schema.
5. Apply database migrations for the worker-owned schema before ingestion begins.
6. Insert new detections into PostGIS.
7. Avoid duplicate inserts across repeated polling runs.

## Ingestion Contract

### Query Shape

Each polling cycle must first run:

- `FirmsClient.data_availability(source="ALL")`

Each polling cycle must run `FirmsClient.area(...)` once per source using the following parameters:

- `area=-179.2,18.9,-66.9,71.4`
- `day_range=1`
- `source=VIIRS_SNPP_NRT`
- `source=VIIRS_NOAA20_NRT`
- `source=VIIRS_NOAA21_NRT`

The worker must treat the `source` argument passed to `FirmsClient.area(...)` as the canonical source/satellite identifier for every returned row. It must not derive the stored `satellite` field from FIRMS row payload fields such as `satellite`.

Before issuing `FirmsClient.area(...)` for a configured source, the worker must verify that the source is present in the `data_id` column returned by `FirmsClient.data_availability(source="ALL")`.

- if the configured source is present, the worker may issue the `area(...)` request
- if the configured source is not present, the worker must log an error and skip the `area(...)` request for that source during that cycle

### Date Handling

The worker must determine the current date in UTC before running FIRMS area queries.

For each configured source:

- the worker must read that source's `max_date` from `FirmsClient.data_availability(source="ALL")`
- the worker must first check whether the current UTC date is available for that source
- if the current UTC date is less than or equal to `max_date`, the worker must call `FirmsClient.area(...)` and explicitly pass `date=<current UTC date>`
- if the current UTC date is not available, the worker must then check whether the previous UTC date is available for that source
- if the previous UTC date is less than or equal to `max_date`, the worker must call `FirmsClient.area(...)` and explicitly pass `date=<previous UTC date>`
- if neither the current UTC date nor the previous UTC date is available, the worker must log an error and skip the `area(...)` query for that source during that cycle

The worker must not rely on FIRMS default no-date behavior for retrieving the latest available data.

### Time Zone Policy

All worker-managed timestamps must use UTC.

- FIRMS `acquisition_time` values are interpreted as UTC.
- `ingest_time`, `created_at`, and `updated_at` must be written as UTC timestamps.
- Any worker logging or cycle timing should also use UTC.

## Processing Flow

For each polling cycle, the worker must:

1. Record the cycle start time in UTC.
2. Execute `FirmsClient.data_availability(source="ALL")`.
3. Determine the current UTC date for the cycle.
4. For each configured source, confirm that it appears in the returned `data_id` values.
5. For each configured source, read the source `max_date`.
6. For each configured source, first check whether the current UTC date is available.
7. If the current UTC date is not available, check whether the previous UTC date is available.
8. Execute one FIRMS area query per configured source that passed the availability check, explicitly passing either `date=<current UTC date>` or `date=<previous UTC date>` according to the selection rule above.
9. Combine the returned rows into a single processing stream.
10. Normalize each FIRMS row into the database schema.
11. Generate a deterministic `source_key` for deduplication.
12. Insert records into PostGIS using the duplicate-handling policy defined below.
13. Record ingestion timestamps for observability and troubleshooting.

Before entering the polling loop, the worker must apply all pending database migrations.

## Deduplication

The worker will poll more frequently than the underlying VIIRS feeds update. Repeated polling must not create duplicate rows.

Each normalized point must include a deterministic `source_key` used to identify the same source observation across polling cycles.

### `source_key` Definition

`source_key` is the unique identifier for a VIIRS point and must be derived from:

- `latitude`
- `longitude`
- `acquisition_time`
- `satellite`

Normalization rules for key generation:

- `latitude` and `longitude` must be rounded to 5 decimal places before key generation.
- `acquisition_time` must use FIRMS minute precision.
- `satellite` must be exactly the FIRMS query `source` string used for the request.
- Field ordering must be `latitude`, `longitude`, `acquisition_time`, `satellite`.
- The resulting key must be a deterministic string representation of that ordered tuple.

The database must enforce uniqueness on `source_key`.

## Storage Contract

The worker writes to the PostGIS table `public.points`.

The worker owns the schema required for ingestion and must create or update it through migrations stored in the repository.

### Migration Contract

The worker migration system must:

- store migration files in a versioned local directory under source control
- apply pending migrations before the polling loop starts
- track applied migrations in a database table named `public.schema_migrations`
- execute each migration at most once
- fail fast and stop worker startup if a migration cannot be applied

Each migration record must include at minimum:

- `version` as the unique migration identifier
- `applied_at` as a UTC timestamp

### Columns

#### Identity

| Column | Type | Nullability | Notes |
| --- | --- | --- | --- |
| `id` | `uuid` | not null | Internal primary key. |
| `source_key` | `text unique` | not null | Deterministic deduplication key. |

#### Source Metadata

| Column | Type | Nullability | Notes |
| --- | --- | --- | --- |
| `satellite` | `text` | not null | Exact FIRMS query source string such as `VIIRS_SNPP_NRT` or `VIIRS_NOAA20_NRT`. |
| `version_tag` | `text` | null | Source or dataset version identifier. |
| `raw_payload` | `jsonb` | not null | Original FIRMS row for traceability and reprocessing. Default `{}` if needed. |

#### Temporal Fields

| Column | Type | Nullability | Notes |
| --- | --- | --- | --- |
| `acquisition_time` | `timestamptz` | not null | Time of the original observation in UTC. |
| `ingest_time` | `timestamptz` | not null | Time the worker retrieved and stored the row in UTC. |
| `created_at` | `timestamptz` | not null | Row creation timestamp. |
| `updated_at` | `timestamptz` | not null | Last row update timestamp. |

#### Spatial Fields

| Column | Type | Nullability | Notes |
| --- | --- | --- | --- |
| `latitude` | `double precision` | not null | WGS84 latitude. |
| `longitude` | `double precision` | not null | WGS84 longitude. |
| `geom` | `geometry(Point, 4326)` | not null | PostGIS point geometry derived from latitude and longitude. |

#### Fire Detection Attributes

| Column | Type | Nullability | Notes |
| --- | --- | --- | --- |
| `confidence` | `text` | null | Confidence as provided by FIRMS after string normalization. |
| `frp` | `double precision` | null | Fire radiative power. |
| `bright_ti4` | `double precision` | null | FIRMS `bright_ti4` value. |
| `bright_ti5` | `double precision` | null | FIRMS `bright_ti5` value. |
| `scan` | `double precision` | null | Pixel width in scan direction. |
| `track` | `double precision` | null | Pixel height in track direction. |
| `daynight` | `text` | null | Day or night indicator from FIRMS. |

## Normalization Rules

The worker must normalize FIRMS response rows into the `public.points` table shape.

Required baseline transformations:

- combine FIRMS `acq_date` and `acq_time` into `acquisition_time`
- interpret `acquisition_time` as UTC
- set `satellite` from the `source` argument used for the `FirmsClient.area(...)` request
- populate `geom` from longitude and latitude in SRID 4326
- retain the original FIRMS row in `raw_payload`
- map FIRMS `version` into `version_tag`
- map FIRMS `bright_ti4` into `bright_ti4`
- map FIRMS `bright_ti5` into `bright_ti5`
- store FIRMS `confidence` as text

## Database Behavior

The storage layer must support deduplicated writes based on `source_key`.

Write policy:

- insert new rows when `source_key` is not present
- ignore duplicates when `source_key` already exists
- do not upsert or refresh existing VIIRS rows

VIIRS detections are treated as immutable source observations. Only the first observation of a new point is stored.

The `public.points` table, its uniqueness constraint, and any supporting extensions or indexes required by this specification must be created and maintained by the worker migration system.

## Error Handling

The worker must be tolerant of malformed FIRMS responses.

- if FIRMS returns malformed data for an execution, that execution must be skipped
- skipped data is retried implicitly on the next scheduled poll
- duplicate protection must still make repeated polling idempotent
- if `data_availability(source="ALL")` does not list a configured source, the worker must log the condition and skip the corresponding `area(...)` request for that cycle
- if neither the current UTC date nor the previous UTC date is available for a configured source, the worker must log the condition and skip the corresponding `area(...)` request for that cycle

Migration failures are startup failures:

- if a pending migration cannot be applied, the worker must stop before polling
- the worker must not continue into ingestion with a partially updated schema

This specification assumes a single worker instance is running. The separate FastAPI process is read-only with respect to the `public.points` table.

## Operational Expectations

- polling interval target: every 5 minutes
- data window target: latest available 24 hours from FIRMS
- geographic coverage: North America bounding box only
- source coverage: `VIIRS_SNPP_NRT`, `VIIRS_NOAA20_NRT`, and `VIIRS_NOAA21_NRT`
- database target: PostGIS
- worker concurrency: single writer instance
- migration execution: once at worker startup before polling

## Implementation Notes

- store migrations as ordered `.sql` files
- apply migrations before constructing the steady-state polling loop
- preserve enough source metadata to allow future reprocessing without calling FIRMS again
- expect FIRMS responses to overlap across polling runs
- rely on the database uniqueness constraint on `source_key` to enforce idempotency
