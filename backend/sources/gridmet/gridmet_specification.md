# GridMET Client Specification v3

## Purpose

Implement a Python client for reading GridMET meteorological data from yearly NetCDF files with per-client local caching and optimized repeated point lookups.

The primary access pattern is point selection by dataset, latitude, longitude, year, and day-of-year, with support for retrieving the most recent available value when no explicit day is provided.

## Scope

The client must support:

- Any GridMET dataset whose remote file follows the `<dataset>_<year>.nc` naming convention
- Local caching of downloaded yearly NetCDF files
- Isolated temporary cache directories per client instance
- In-memory reuse of only the most recently accessed dataset-year pair
- Point lookup by latitude, longitude, year, and day-of-year
- Point lookup for the most recent available data
- Explicit refresh of the current-year file

## Background

GridMET files are distributed as yearly NetCDF files using URLs of the form:

`https://www.northwestknowledge.net/metdata/data/<dataset>_<year>.nc`

Representative sample inspection in this repository confirms the following schema characteristics for at least one GridMET file:

- File format is `NETCDF4`
- Coordinates are named `lat`, `lon`, `day`, and `crs`
- Geographic coordinates use `lat` and `lon`
- Temporal coordinates use `day`
- The CRS metadata is WGS84 / `EPSG:4326`
- The primary data variable name may not match the dataset token in the filename
- Current-year files may be partial and may be updated over time

## Required Dependencies

The implementation is expected to use:

- `xarray`
- A NetCDF backend compatible with `xarray`, such as `netcdf4` or `h5netcdf`
- `requests`
- `pathlib`

## Public API

### Constructor

Provide a client class, name `GridMETClient`.

Recommended optional constructor parameters:

- `base_url: str = "https://www.northwestknowledge.net/metdata/data"`

Example:

```python
client = GridMETClient()
```

### Dataset Helper Class

Provide an optional helper class, recommended name `GridMETDataset`, that exposes string constants for common dataset identifiers.

Purpose:

- highlight commonly used GridMET datasets
- reduce misspellings in calling code
- improve discoverability of common dataset names

The helper class must not replace string inputs in the public API.

Requirements:

- `sel(...)` must accept plain strings for `dataset`
- `sel(...)` must also work when passed a constant from `GridMETDataset`
- `refresh_latest(...)` must accept plain strings for `dataset`
- `refresh_latest(...)` must also work when passed a constant from `GridMETDataset`
- `GridMETDataset` constants must be plain strings, not enums or custom objects
- The helper class is advisory only and must not act as a fixed allowlist

Example shape:

```python
class GridMETDataset:
    FM100 = "fm100"
    FM1000 = "fm1000"
    ERC = "erc"
    BI = "bi"
```

Example usage:

```python
client = GridMETClient()
client.sel(GridMETDataset.FM1000, 34.5, -119.7, 2026, 107)
client.sel("fm1000", 34.5, -119.7)
```

### Selection Methods

The client must support two selection forms:

```python
sel(dataset: str, lat: float, lon: float, year: int, day: int)
sel(dataset: str, lat: float, lon: float)
```

Required behavior:

- `sel(dataset, lat, lon, year, day)` returns the value for the requested dataset at the requested location and exact calendar day represented by the given year and day-of-year
- `sel(dataset, lat, lon)` returns the most recent available value for the requested dataset at the requested location

Day and year requirements:

- `year` identifies the yearly NetCDF file to read
- `day` is the calendar day-of-year within that `year`, starting at `1`
- The explicit selection API must not accept `datetime.date` or `datetime.datetime`
- The selected slice is calendar-day based only; there is no time-of-day selection mechanism in the public API

Return type:

- Both `sel` forms must return a scalar Python numeric value
- The return value should reflect normal `xarray` decoding of the NetCDF variable, including scale and offset handling

### Refresh Method

The client must expose an explicit method for refreshing the current-year file:

```python
refresh_latest(dataset: str) -> None
```

Required behavior:

- `refresh_latest(dataset)` checks whether the requested dataset's current calendar year remote file has changed
- If the current-year file is missing locally, `refresh_latest(dataset)` downloads it
- If the remote current-year file has changed, `refresh_latest(dataset)` replaces the local cached file
- If the active in-memory dataset corresponds to the refreshed dataset and year, the client must reload it after refresh
- If the current calendar year's file does not exist remotely, `refresh_latest(dataset)` must fall back to the most recent prior year using the same fallback rules as `sel(dataset, lat, lon)`
- When fallback occurs, the located fallback year becomes the latest locally available year for that dataset until a newer year is later downloaded

API intent:

- `refresh_latest(dataset)` is the explicit network-refresh entry point for near-real-time data
- `sel(dataset, lat, lon)` must not implicitly perform remote freshness checks

### Cache Inspection Methods

The client should expose lightweight cache inspection helpers for debugging and verification.

```python
@property
cache_root() -> Path

@property
cache_root_if_present() -> Path | None

cache_path(dataset: str, year: int) -> Path
```

Required behavior:

- `cache_root` returns the client-owned cache root and creates it if it does not already exist
- `cache_root_if_present` returns the existing client-owned cache root without creating a new one
- `cache_path(dataset, year)` returns the on-disk cache path for the requested dataset-year pair
- `cache_path(dataset, year)` must validate `dataset`
- `cache_path(dataset, year)` must validate `year`
- `cache_path(dataset, year)` may create the cache root and dataset directory as part of path materialization

API intent:

- these helpers are for observability, debugging, and tests
- `cache_root_if_present` exists specifically so callers can verify `clear()` behavior without recreating a cache root as a side effect

### Clear Method

The client must expose an explicit method for releasing all local resources:

```python
clear() -> None
```

Required behavior:

- `clear()` must close any currently loaded in-memory dataset handle
- `clear()` must delete all cached dataset files under the client-owned cache root
- `clear()` must delete the client-owned cache root directory itself
- After `clear()` returns, the client must hold no open dataset handles
- `clear()` must be safe to call more than once
- After `clear()` returns, the client remains usable
- The next call to `sel(...)` or `refresh_latest(...)` must recreate a new client-owned temporary cache root automatically

API intent:

- `clear()` is the primary cleanup entry point for deterministic resource release
- Destructor-driven cleanup is a fallback only and should delegate to the same cleanup logic when possible

## Functional Requirements

### 1. Dataset Argument Validation

The dataset is supplied per call rather than being bound at construction time.

Requirements:

- Validate the dataset name on every public method call that accepts `dataset`
- Reject empty or unsafe dataset names
- Use the dataset name directly in file naming and URL generation
- Accept either a plain string or a string constant provided by `GridMETDataset`
- Apply the same dataset validation to `cache_path(dataset, year)`

Dataset-name validation rule:

- Dataset names must match the regular expression `^[A-Za-z0-9_]+$`

Examples of valid dataset identifiers include:

- `fm100`
- `fm1000`
- `erc`
- `bi`

The implementation must not rely on a fixed allowlist.

The helper class may define common dataset identifiers, but the client must continue to support any valid dataset string that matches the naming rules and resolves to a real GridMET file.

### 2. Yearly File Naming and URL Resolution

The client must construct yearly filenames in this format:

`<dataset>_<year>.nc`

The remote URL format is:

`<base_url>/<dataset>_<year>.nc`

Example:

`https://www.northwestknowledge.net/metdata/data/fm1000_2026.nc`

### 3. Cache Location and Ownership

The client must store downloaded files locally. Cached files for different datasets must coexist within the same client-owned cache root.

Recommended cache layout:

`<cache_dir>/<dataset>/<dataset>_<year>.nc`

Example:

`.gridmet-bakDovZf483/fm1000/fm1000_2026.nc`

Requirements:

- Create cache directories as needed
- Reuse an existing cached file for the requested historical year without remote revalidation
- Download missing files into the cache
- The specification does not define or support shared cache directories across multiple client instances

Temporary-cache requirements:

- The client must create a unique temporary cache directory during construction
- The client-owned temporary cache directory name should begin with `.`
- The temporary directory name must be random enough to avoid collisions between concurrent client instances
- The temporary cache directory is owned by that client instance

### 4. Temporary Cache Cleanup

When the client is cleared, all client-owned cached files and directories must be removed. If the client goes out of scope without an explicit `clear()`, the destructor should attempt the same cleanup on a best-effort basis.

Requirements:

- `clear()` must attempt to close any open in-memory dataset handles before deleting cached files
- `clear()` must delete the entire client-owned temporary cache directory recursively
- Destructor-based cleanup should call the same cleanup routine as `clear()` when possible
- Cleanup must be idempotent and must not fail simply because the cache directory is already absent
- After `clear()`, the client must be able to lazily recreate a new temporary cache directory on the next operation that requires caching

### 5. In-Memory Dataset Reuse

The client must keep only one dataset-year pair loaded in memory at a time.

Requirements:

- Track the dataset and year currently loaded in memory
- Reuse the loaded dataset for repeated accesses to that same dataset and year
- When a different dataset or year is requested, unload or replace the in-memory dataset with the newly requested dataset-year pair

This is an explicit optimization goal for repeated point lookups against the same dataset and year.

### 6. Explicit-Day Selection

For `sel(dataset, lat, lon, year, day)`:

- Validate inputs
- Validate `dataset`
- Validate `year`
- Validate `day`
- Ensure the requested year file is available locally, downloading if necessary
- Load the requested dataset-year pair into memory if it is not already active
- Resolve the requested latitude and longitude against the GridMET grid
- Resolve the requested calendar day against the dataset `day` coordinate
- Return the selected value

Selection behavior:

- Latitude and longitude selection will use nearest-neighbor logic.
- Day selection should map to the dataset `day` coordinate using the exact calendar date derived from `year` and `day`

Point-selection rule:

- Latitude and longitude selection must use `xarray` nearest-neighbor semantics against `lat` and `lon`
- The returned scalar value must come from the selected nearest grid point and exact requested calendar day

Year/day validation requirements:

- `year` must be an integer
- `day` must be an integer day-of-year
- `year` must not exceed the current calendar year
- `day` must be valid for the supplied year
- Missing or partially supplied `year`/`day` inputs must raise `ValueError`
- The implementation must fail clearly if the requested date is not present in the target NetCDF file

### 7. Most-Recent Selection

For `sel(dataset, lat, lon)`:

- Validate `dataset`
- Determine the most recent relevant year
- Ensure the corresponding current-year file for the requested dataset is available locally
- Return the most recent available value at the requested latitude and longitude

The "most recent available value" means the last available slice in the currently published current-year file, not necessarily the current date.

Most-recent year rule:

- The client must first use the locally cached current calendar year file for the requested dataset if it exists
- If the current-year file is not cached locally, the client may download it
- If the current-year file does not exist remotely, the client must fall back to the previous year
- The fallback search must continue backward by year until a file is found or year `1979` is reached
- If no file is found through year `1979`, the client must raise `GridMETDownloadError`

### 8. Current-Year Refresh

`refresh_latest(dataset)` is responsible for updating the current-year cached file for the requested dataset when newer remote data are available.

Acceptable refresh strategies include:

- compare HTTP `Last-Modified`
- compare `ETag`
- compare remote content length
- redownload conditionally using request headers if supported

Requirements:

- `refresh_latest(dataset)` must validate `dataset`
- `refresh_latest(dataset)` must not blindly assume the cached current-year file is current
- If the remote file has changed, replace the cached file
- If a cached file was replaced it becomes the latest on-disk copy for that dataset-year
- If the active in-memory dataset corresponds to the refreshed dataset and year, reload it after refresh

Required refresh strategy:

- The client must issue an HTTP `HEAD` request for the current-year file of the requested dataset when `refresh_latest(dataset)` is called
- If `ETag` is present, it must be used as the primary freshness signal
- Otherwise, if `Last-Modified` is present, it must be used
- Otherwise, `Content-Length` may be used as a fallback signal
- If the freshness signal differs from the client's known local state for the cached file, the file must be redownloaded
- If the server does not provide any usable freshness signal, the client must conservatively redownload the current-year file when `refresh_latest(dataset)` is called

### 9. Schema Handling

The client must assume the schema observed in the sample file:

- coordinates: `lat`, `lon`, `day`, `crs`
- point selection dimensions: `day`, `lat`, `lon`
- CRS metadata: WGS84 / `EPSG:4326`

The client must not assume that the primary data variable name equals the dataset token.

Recommended approach:

- Identify the primary data variable as the main non-coordinate variable with dimensions including `day`, `lat`, and `lon`

Primary-variable selection rule:

- If exactly one non-coordinate data variable has dimensions `('day', 'lat', 'lon')`, that variable is the primary variable
- If no such variable exists, raise `GridMETDataError`
- If multiple such variables exist, raise `GridMETDataError` rather than guessing

If the file does not match the expected point-selection schema, raise `GridMETDataError`.

The implementation must support the sample-observed case where `day` is decoded by `xarray` into datetime-like coordinates.

### 10. Error Handling

The implementation must fail with clear, actionable exceptions for:

- Invalid dataset name
- Invalid latitude or longitude
- Invalid year/day input
- Missing or inaccessible remote file
- Download failure
- Corrupt or unreadable NetCDF file
- Unexpected dataset schema
- Failure to identify the primary data variable
- Failure to create or clean up a client-owned temporary cache directory

Recommended exception strategy:

- `ValueError` for invalid caller inputs
- `GridMETDownloadError` for network or download failures
- `GridMETDataError` for unreadable, invalid, or schema-incompatible NetCDF contents
- `GridMETCacheError` for cache directory creation, replacement, or cleanup failures

### 11. Input Validation

Minimum validation requirements:

- `dataset` must be non-empty and safe for filename/URL construction
- `year`, when provided, must be an integer
- `day`, when provided, must be an integer day-of-year valid for the supplied year
- the provided `year` must not exceed the current calendar year
- `lat` and `lon` must be numeric
- `cache_path(dataset, year)` must reject non-integer `year` values

Coordinate validation rule:

- Latitude must be within `[-90, 90]`
- Longitude must be within `[-180, 180]`

The client does not need to reject coordinates outside the GridMET domain before loading the file, but it must fail clearly if selection cannot be resolved.

### 12. Performance Expectations

The design is optimized for workloads with many repeated queries against one dataset and one year at a time.

Implications:

- Disk caching avoids repeated downloads
- Single dataset-year in-memory reuse avoids repeated dataset opens
- Switching datasets or years may incur a reload cost by design
- Per-client cache isolation avoids multi-client cache update coordination
- Explicit refresh avoids hidden network activity during ordinary point lookups

## Recommended Internal API

The implementation may include helpers such as:

- `_validate_dataset(dataset: str) -> str`
- `_validate_year_day(year: int, day: int) -> tuple[int, int]`
- `_date_from_year_day(year: int, day: int) -> date`
- `_build_filename(year: int) -> str`
- `_build_url(dataset: str, year: int) -> str`
- `_get_cache_path(dataset: str, year: int) -> Path`
- `_replace_cache_file(dataset: str, year: int, source_path: Path) -> Path`
- `_download_to_cache(dataset: str, year: int) -> Path`
- `_refresh_latest(dataset: str) -> None`
- `_clear() -> None`
- `_load_year(dataset: str, year: int) -> xr.Dataset`
- `_get_primary_variable(ds: xr.Dataset) -> xr.DataArray`
- `_select_point(ds: xr.Dataset, lat: float, lon: float, year: int | None, day: int | None)`

These are recommendations, not required public API.

## Non-Functional Requirements

### Reliability

- Cached files must not be silently corrupted by partial writes
- Current-year refresh logic must not leave the cache in an inconsistent state
- The client must behave deterministically for the same cached file and inputs
- A client-owned temporary cache directory must never resolve to or delete a path outside that client-owned directory
- `clear()` must leave no open in-memory dataset handle and no remaining client-owned cached files on success

### Maintainability

- URL construction, cache handling, refresh logic, and point selection should be separated cleanly
- The public API should stay small
- Dataset-specific logic should be minimized

### Testability

The implementation should be testable for:

- filename and URL generation
- helper-class dataset constants behaving identically to equivalent plain strings
- cache path generation
- cache inspection helpers exposing creation and deletion state correctly
- temporary cache directory generation
- initial download behavior
- cached reuse behavior
- explicit `clear()` cleanup behavior
- destructor fallback cleanup behavior
- single dataset-year in-memory reuse behavior
- year switch reload behavior
- dataset switch reload behavior
- explicit refresh behavior for current-year queries
- point selection behavior
- failure behavior for invalid schema or missing variables

## Suggested Test Cases

- Constructing the client succeeds without a dataset argument
- `sel(GridMETDataset.FM1000, lat, lon, year, day)` succeeds
- `sel("invalid dataset!", lat, lon, year, day)` raises `ValueError`
- `sel(dataset, lat, lon, year, day)` downloads a missing historical file and returns a value
- `cache_root` creates and returns a hidden client-owned cache root
- `cache_root_if_present` does not create a cache root when none exists
- `cache_path(dataset, year)` returns the expected dataset-year cache path
- Repeating `sel(dataset, lat, lon, same_year, same_day)` reuses the in-memory dataset
- Switching from one year to another replaces the in-memory dataset
- Switching from one dataset to another replaces the in-memory dataset
- Cached historical files are reused without redownloading
- `clear()` closes the active in-memory dataset handle
- `clear()` deletes cached dataset files and the client-owned cache directory
- Calling `clear()` twice does not fail
- `sel(...)` or `refresh_latest(...)` after `clear()` recreates a new cache directory automatically
- Destroying a client without calling `clear()` attempts the same cleanup on a best-effort basis
- `sel(dataset, lat, lon)` uses the current-year file and returns the latest available value
- `sel(dataset, lat, lon)` falls back to prior years if the current-year file does not exist
- `sel(dataset, lat, lon)` does not implicitly perform a remote freshness check
- `refresh_latest(dataset)` refreshes the current-year cache when the remote file has changed
- `refresh_latest(dataset)` redownloads the current-year file if no freshness signal is available
- `refresh_latest(dataset)` reloads the in-memory dataset when needed
- Missing primary variable raises a data/schema error
- Multiple candidate primary variables raise a data/schema error
- Invalid year/day input raises `ValueError`
- Invalid latitude or longitude raises `ValueError`
- Nearest-neighbor selection returns a value at the closest grid point

## Acceptance Criteria

This specification is satisfied when:

- A Python client class exists with a constructor that does not require a dataset argument
- A `GridMETDataset` helper class exists for common dataset string constants
- The client supports any dataset following the `<dataset>_<year>.nc` convention
- The client accepts both plain dataset strings and `GridMETDataset` string constants in `sel(...)` and `refresh_latest(...)`
- Local caching is implemented
- Cache inspection helpers are implemented
- `clear()` is implemented for explicit cleanup
- `clear()` deletes client-owned cached files and cache directories
- The client remains usable after `clear()`
- Only the most recently accessed dataset-year pair is kept loaded in memory
- `sel(dataset, lat, lon, year, day)` is implemented
- `sel(dataset, lat, lon)` is implemented
- `refresh_latest(dataset)` is implemented for explicit current-year refresh
- `sel(dataset, lat, lon)` does not require implicit remote freshness detection
- Most-recent queries fall back to earlier years if the current-year file is unavailable
- Point selection works against the GridMET coordinate schema
- `sel` returns scalar numeric values
- Invalid inputs and download/schema failures produce clear exceptions

## Directory Structure

Do not create a monolithic python file. The implementation should be split into multiple individualized files.

Below is an example of a recommended structure and not a strict requirement:
- __init__.py
- cache.py
- errors.py
- models.py
- client.py
