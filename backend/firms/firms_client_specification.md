# FIRMS Client

This directory exists to explain how to implement a Python client for the NASA FIRMS API using the examples stored alongside this document.

Base URL: `https://firms.modaps.eosdis.nasa.gov`

The local files in this directory show these API families in use:

| Service | Purpose | Response Type | Local Evidence |
| --- | --- | --- | --- |
| `map_key` | Check map key status, rate limit, and current usage | JSON | `samples/firms.modaps.eosdis.nasa.gov.json` |
| `area` | Query active fire hotspots for a bounding box or `world` | CSV | `samples/area-sample-world.csv`, `samples/area-sample-coords.csv` |
| `data_availability` | List valid source IDs and available date ranges | CSV | `samples/data_availability-all.csv`, `samples/data_availability-VIRRS_NOAA20_NRT.csv` |
| `countries` | List supported countries and 3-letter country codes | Likely tabular/text output | Mentioned in `tests/firms_api_use.ipynb` |
| `country` | Query fire detections by country code | CSV | Mentioned in `tests/firms_api_use.ipynb` |
| `kml_fire_footprints` | Download regional fire footprint KML/KMZ data | KML/KMZ | `samples/FirespotArea_SUOMI_VIIRS_C2_Alaska_24h.kmz` |

## Implementation Goal

The Python client should do four things well:

1. Build correct FIRMS URLs.
2. Validate inputs before sending requests.
3. Parse JSON, CSV, and binary KMZ/KML responses cleanly.
4. Provide a small, typed interface that another AI or developer can call without needing to remember raw endpoint shapes.

## Recommended Python Design

Use a small class around a reusable `requests.Session`.

Suggested public methods:

- `ok() -> bool`
- `remaining() -> int`
- `map_key_status() -> dict`
- `data_availability(source: str = "ALL") -> pandas.DataFrame`
- `area(source: str, area: str | tuple[float, float, float, float], day_range: int, date: str | datetime.date | None = None) -> pandas.DataFrame`
- `countries(format: str | None = None) -> str | bytes`
- `country(source: str, country_code: str, day_range: int, date: str | datetime.date | None = None) -> pandas.DataFrame`
- `kml_fire_footprints(region: str, date_span: str, sensor: str) -> bytes`

Use helper methods for:

- `_normalize_date(...)`
- `_normalize_area(...)`
- `_request(...)`
- `_get_json(...)`
- `_get_csv_frame(...)`

## Optional String Constant Classes

The client methods should continue accepting plain strings. Do not make `FirmsClient` depend on enum members or constant classes internally.

These helper classes exist only to reduce typos when calling the client:

- source dataset IDs for `area(...)`, `country(...)`, and `data_availability(...)`
- KML footprint sensors
- KML regions
- KML date spans

Recommended approach:

- define simple classes containing uppercase string constants
- keep the values exactly equal to the API path segments
- allow callers to use either raw strings or these constants

Example:

```python
client.area(FirmsSource.VIIRS_SNPP_NRT, "world", 1)
client.kml_fire_footprints(FirmsRegion.ALASKA, FirmsDateSpan.H24, FirmsFootprintSensor.SUOMI_NPP_VIIRS_C2)
```

Reference shape:

```python
class FirmsSource:
    MODIS_NRT = "MODIS_NRT"
    MODIS_SP = "MODIS_SP"
    VIIRS_NOAA20_NRT = "VIIRS_NOAA20_NRT"
    VIIRS_NOAA20_SP = "VIIRS_NOAA20_SP"
    VIIRS_NOAA21_NRT = "VIIRS_NOAA21_NRT"
    VIIRS_SNPP_NRT = "VIIRS_SNPP_NRT"
    VIIRS_SNPP_SP = "VIIRS_SNPP_SP"
    LANDSAT_NRT = "LANDSAT_NRT"
    GOES_NRT = "GOES_NRT"
    BA_MODIS = "BA_MODIS"
    BA_VIIRS = "BA_VIIRS"


class FirmsFootprintSensor:
    MODIS_C61 = "c6.1"
    LANDSAT = "landsat"
    SUOMI_NPP_VIIRS_C2 = "suomi-npp-viirs-c2"
    NOAA20_VIIRS_C2 = "noaa-20-viirs-c2"
    NOAA21_VIIRS_C2 = "noaa-21-viirs-c2"


class FirmsRegion:
    CANADA = "canada"
    ALASKA = "alaska"
    USA_CONTIGUOUS_AND_HAWAII = "usa_contiguous_and_hawaii"
    CENTRAL_AMERICA = "central_america"
    SOUTH_AMERICA = "south_america"
    EUROPE = "europe"
    NORTHERN_AND_CENTRAL_AFRICA = "northern_and_central_aftrica"
    SOUTHERN_AFRICA = "southern_aftrica"
    RUSSIA_ASIA = "russia_asia"
    SOUTH_ASIA = "south_asia"
    SOUTHEAST_ASIA = "southeast_asia"
    AUSTRALIA_NEWZEALAND = "australia_newzealand"


class FirmsDateSpan:
    H24 = "24h"
    H48 = "48h"
    H72 = "72h"
    D7 = "7d"
```

Notes:

- These are convenience constants, not validation rules.
- The client should still accept any raw string the API supports.
- If the API adds new values later, callers should still be able to pass them directly before the constants are updated.

## Known Endpoint Shapes

### 1. Map Key Status

Checks current transaction information for the API key.

Path:

```text
/mapserver/mapkey_status/?MAP_KEY={MAP_KEY}
```

Example local response:

```json
{ "transaction_limit" : 5000, "current_transactions": 0, "transaction_interval" : "10 minutes" }
```

Expected Python method:

```python
def map_key_status(self) -> dict:
    ...
```

Additional convenience methods should build on this endpoint:

```python
def ok(self) -> bool:
    ...


def remaining(self) -> int:
    ...
```

Behavior:

- `ok()` should return `True` when the FIRMS service can be reached and `map_key_status()` succeeds.
- `ok()` should return `False` if the request fails for connectivity, timeout, authentication, or HTTP reasons.
- `remaining()` should return the number of transactions left in the current rate-limit window.
- `remaining()` should be derived from `transaction_limit - current_transactions`.
- `remaining()` should raise if `map_key_status()` fails or if the expected response fields are missing.

### 2. Data Availability

Lists valid dataset IDs and their available date ranges.

Path:

```text
/api/data_availability/csv/{MAP_KEY}/{SOURCE}
```

Parameters:

- `MAP_KEY`: required API key
- `SOURCE`: `ALL` or a specific source such as `VIIRS_NOAA20_NRT`

Examples from this directory:

- `/api/data_availability/csv/[MAP_KEY]/ALL`
- `/api/data_availability/csv/[MAP_KEY]/VIIRS_NOAA20_NRT`

Observed CSV columns:

```text
data_id,min_date,max_date
```

This endpoint is useful because it tells the client which source IDs are valid and what date ranges can be queried.

### 3. Area

Queries hotspot detections for a bounding box or the whole world.

Path:

```text
/api/area/csv/{MAP_KEY}/{SOURCE}/{AREA_COORDINATES}/{DAY_RANGE}
/api/area/csv/{MAP_KEY}/{SOURCE}/{AREA_COORDINATES}/{DAY_RANGE}/{DATE}
```

Important detail:

- `DATE` is optional.
- The notebooks in `tests/firms_api_use.ipynb` show successful requests without a date, for example:
  - `/api/area/csv/{MAP_KEY}/VIIRS_NOAA20_NRT/world/1`
  - `/api/area/csv/{MAP_KEY}/VIIRS_NOAA20_NRT/54,5.5,102,40/3`

Parameters:

- `MAP_KEY`: required API key
- `SOURCE`: a FIRMS dataset ID such as `VIIRS_SNPP_NRT` or `VIIRS_NOAA20_NRT`
- `AREA_COORDINATES`:
  - either the literal string `world`
  - or `west,south,east,north`
- `DAY_RANGE`: local docs say `1` to `5`
- `DATE`: optional start/end anchor in `YYYY-MM-DD`

Semantics from the current notes:

- If `DATE` is present, the time window is `DATE` back through `DATE - (DAY_RANGE - 1)`.
- `world` corresponds to `-180,-90,180,90`.

Observed CSV columns in the sample files:

```text
latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
```

Practical warning:

- The notebook notes that world-scale VIIRS queries can return tens of thousands of rows per day.
- The client should not assume small responses.

### 4. Countries

Lists supported countries and their 3-letter country codes for use with country-based queries.

Path:

```text
/api/countries
```

Also referenced:

```text
/api/countries/?format=html
```

Use this endpoint as metadata lookup for the `country(...)` method.

Because this directory does not include a saved sample response, the client should treat this endpoint as a passthrough metadata call unless stricter parsing is later confirmed.

### 5. Country

Returns fire detection hotspots in CSV format for a single country code, source, and time window.

Path:

```text
/api/country/csv/{MAP_KEY}/{SOURCE}/{COUNTRY_CODE}/{DAY_RANGE}
/api/country/csv/{MAP_KEY}/{SOURCE}/{COUNTRY_CODE}/{DAY_RANGE}/{DATE}
```

Observed example in the notebook:

```text
/api/country/csv/{MAP_KEY}/MODIS_NRT/PER/4
```

Parameters:

- `MAP_KEY`: required API key
- `SOURCE`: dataset ID
- `COUNTRY_CODE`: 3-letter code from `/api/countries`
- `DAY_RANGE`: likely same semantics as `area`
- `DATE`: likely optional, matching the `area` pattern

Notebook warning:

- This is not recommended for large countries such as the USA, China, Canada, and Russia because polygon complexity may cause timeouts.

### 6. KML Fire Footprints

Downloads regional footprint data in KML/KMZ form.

Path pattern from the current notes:

```text
/api/kml_fire_footprints/{REGION}/{DATE_SPAN}/{SENSOR}/FirespotArea_{...}
```

The saved sample file strongly suggests the actual request is a downloadable KMZ/KML resource under:

```text
/api/kml_fire_footprints/{REGION}/{DATE_SPAN}/{SENSOR}/...
```

Known parameter values from the current notes:

- `REGION`: examples include `alaska`, `canada`, `europe`, `central_america`, `south_america`
- `DATE_SPAN`: `24h`, `48h`, `72h`, `7d`
- `SENSOR`:
  - `c6.1`
  - `landsat`
  - `suomi-npp-viirs-c2`
  - `noaa-20-viirs-c2`
  - `noaa-21-viirs-c2`

Because this endpoint returns a file, the client should expose it as raw bytes and optionally provide a helper to write it to disk.

## Validation Rules

The client should validate these inputs before sending a request.

### API Key

- Must be a non-empty string.

### Date

- Accept either `datetime.date` or `YYYY-MM-DD`.
- Normalize to `YYYY-MM-DD`.

### Day Range

- Validate as integer.
- Local notes say the supported range is `1` through `5`.

### Area Coordinates

Accept either:

- the exact string `world`
- a 4-tuple/list `(west, south, east, north)`
- a string `"west,south,east,north"`

Validation rules:

- `west >= -180`
- `east <= 180`
- `south >= -90`
- `north <= 90`
- `west < east`
- `south < north`

Normalize numeric areas to a comma-separated string with no spaces.

### Source IDs

Do not hardcode the source list permanently. Prefer:

1. calling `data_availability("ALL")`
2. validating requested source IDs against the returned `data_id` values

Observed source IDs in local samples:

- `MODIS_NRT`
- `MODIS_SP`
- `VIIRS_NOAA20_NRT`
- `VIIRS_NOAA20_SP`
- `VIIRS_NOAA21_NRT`
- `VIIRS_SNPP_NRT`
- `VIIRS_SNPP_SP`
- `LANDSAT_NRT`
- `GOES_NRT`
- `BA_MODIS`
- `BA_VIIRS`

## Error Handling

The client should raise explicit exceptions instead of returning partial failures silently.

Recommended exception hierarchy:

```python
class FirmsError(Exception):
    pass


class FirmsHTTPError(FirmsError):
    pass


class FirmsValidationError(FirmsError):
    pass
```

Recommended behavior:

- Raise `FirmsValidationError` for invalid dates, areas, or day ranges.
- Raise `FirmsHTTPError` for non-2xx responses.
- Include the request URL and response text snippet in HTTP errors when possible.
- Use a request timeout.

## CSV Parsing

The FIRMS notebooks in this workspace use pandas DataFrames as the main representation for CSV responses, so the client should return `pandas.DataFrame` objects for CSV endpoints.

Implementation pattern:

```python
import io
import pandas as pd


def _parse_csv_frame(text: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(text))
```

## Reference Implementation Shape

This is the recommended baseline design for a Python client.

```python
from __future__ import annotations

import datetime as dt
import io
from dataclasses import dataclass

import pandas as pd
import requests


class FirmsSource:
    MODIS_NRT = "MODIS_NRT"
    MODIS_SP = "MODIS_SP"
    VIIRS_NOAA20_NRT = "VIIRS_NOAA20_NRT"
    VIIRS_NOAA20_SP = "VIIRS_NOAA20_SP"
    VIIRS_NOAA21_NRT = "VIIRS_NOAA21_NRT"
    VIIRS_SNPP_NRT = "VIIRS_SNPP_NRT"
    VIIRS_SNPP_SP = "VIIRS_SNPP_SP"
    LANDSAT_NRT = "LANDSAT_NRT"
    GOES_NRT = "GOES_NRT"
    BA_MODIS = "BA_MODIS"
    BA_VIIRS = "BA_VIIRS"


class FirmsFootprintSensor:
    MODIS_C61 = "c6.1"
    LANDSAT = "landsat"
    SUOMI_NPP_VIIRS_C2 = "suomi-npp-viirs-c2"
    NOAA20_VIIRS_C2 = "noaa-20-viirs-c2"
    NOAA21_VIIRS_C2 = "noaa-21-viirs-c2"


class FirmsRegion:
    CANADA = "canada"
    ALASKA = "alaska"
    USA_CONTIGUOUS_AND_HAWAII = "usa_contiguous_and_hawaii"
    CENTRAL_AMERICA = "central_america"
    SOUTH_AMERICA = "south_america"
    EUROPE = "europe"
    NORTHERN_AND_CENTRAL_AFRICA = "northern_and_central_aftrica"
    SOUTHERN_AFRICA = "southern_aftrica"
    RUSSIA_ASIA = "russia_asia"
    SOUTH_ASIA = "south_asia"
    SOUTHEAST_ASIA = "southeast_asia"
    AUSTRALIA_NEWZEALAND = "australia_newzealand"


class FirmsDateSpan:
    H24 = "24h"
    H48 = "48h"
    H72 = "72h"
    D7 = "7d"


class FirmsError(Exception):
    pass


class FirmsValidationError(FirmsError):
    pass


class FirmsHTTPError(FirmsError):
    pass


@dataclass(slots=True)
class FirmsClient:
    map_key: str
    base_url: str = "https://firms.modaps.eosdis.nasa.gov"
    timeout: float = 30.0

    def __post_init__(self) -> None:
        if not self.map_key or not isinstance(self.map_key, str):
            raise FirmsValidationError("map_key must be a non-empty string")
        self.session = requests.Session()

    def map_key_status(self) -> dict:
        url = f"{self.base_url}/mapserver/mapkey_status/"
        response = self.session.get(url, params={"MAP_KEY": self.map_key}, timeout=self.timeout)
        self._raise_for_status(response)
        return response.json()

    def ok(self) -> bool:
        try:
            self.map_key_status()
            return True
        except (requests.RequestException, ValueError, FirmsError):
            return False

    def remaining(self) -> int:
        status = self.map_key_status()
        try:
            limit = int(status["transaction_limit"])
            used = int(status["current_transactions"])
        except (KeyError, TypeError, ValueError) as exc:
            raise FirmsHTTPError("map_key_status response did not include usable transaction counters") from exc
        return max(0, limit - used)

    def data_availability(self, source: str = "ALL") -> pd.DataFrame:
        url = f"{self.base_url}/api/data_availability/csv/{self.map_key}/{source}"
        response = self.session.get(url, timeout=self.timeout)
        self._raise_for_status(response)
        return self._parse_csv_frame(response.text)

    def area(
        self,
        source: str,
        area: str | tuple[float, float, float, float],
        day_range: int,
        date: str | dt.date | None = None,
    ) -> pd.DataFrame:
        area_part = self._normalize_area(area)
        day_range = self._validate_day_range(day_range)
        parts = [self.base_url, "api", "area", "csv", self.map_key, source, area_part, str(day_range)]
        if date is not None:
            parts.append(self._normalize_date(date))
        url = "/".join(p.strip("/") for p in parts)
        response = self.session.get(url, timeout=self.timeout)
        self._raise_for_status(response)
        return self._parse_csv_frame(response.text)

    def country(
        self,
        source: str,
        country_code: str,
        day_range: int,
        date: str | dt.date | None = None,
    ) -> pd.DataFrame:
        day_range = self._validate_day_range(day_range)
        code = country_code.upper()
        parts = [self.base_url, "api", "country", "csv", self.map_key, source, code, str(day_range)]
        if date is not None:
            parts.append(self._normalize_date(date))
        url = "/".join(p.strip("/") for p in parts)
        response = self.session.get(url, timeout=self.timeout)
        self._raise_for_status(response)
        return self._parse_csv_frame(response.text)

    def countries(self, format: str | None = None) -> str:
        url = f"{self.base_url}/api/countries"
        response = self.session.get(url, params={"format": format} if format else None, timeout=self.timeout)
        self._raise_for_status(response)
        return response.text

    def kml_fire_footprints(self, region: str, date_span: str, sensor: str) -> bytes:
        url = f"{self.base_url}/api/kml_fire_footprints/{region}/{date_span}/{sensor}"
        response = self.session.get(url, timeout=self.timeout)
        self._raise_for_status(response)
        return response.content

    def _normalize_date(self, value: str | dt.date) -> str:
        if isinstance(value, dt.date):
            return value.isoformat()
        try:
            return dt.date.fromisoformat(value).isoformat()
        except Exception as exc:
            raise FirmsValidationError(f"invalid date: {value!r}") from exc

    def _validate_day_range(self, value: int) -> int:
        if not isinstance(value, int) or not (1 <= value <= 5):
            raise FirmsValidationError("day_range must be an integer between 1 and 5")
        return value

    def _normalize_area(self, value: str | tuple[float, float, float, float]) -> str:
        if value == "world":
            return "world"
        if isinstance(value, str):
            parts = value.split(",")
            if len(parts) != 4:
                raise FirmsValidationError("area string must be 'west,south,east,north'")
            coords = tuple(float(x) for x in parts)
        else:
            coords = tuple(float(x) for x in value)
            if len(coords) != 4:
                raise FirmsValidationError("area tuple must have four values")
        west, south, east, north = coords
        if west < -180 or east > 180 or south < -90 or north > 90:
            raise FirmsValidationError("area is outside valid world bounds")
        if west >= east or south >= north:
            raise FirmsValidationError("area bounds must satisfy west < east and south < north")
        return f"{west},{south},{east},{north}"

    def _parse_csv_frame(self, text: str) -> pd.DataFrame:
        return pd.read_csv(io.StringIO(text))

    def _raise_for_status(self, response: requests.Response) -> None:
        if response.ok:
            return
        snippet = response.text[:500] if response.text else ""
        raise FirmsHTTPError(f"{response.status_code} for {response.url}: {snippet}")
```

## Usage Examples

```python
client = FirmsClient(map_key="YOUR_MAP_KEY")

is_available = client.ok()
remaining_calls = client.remaining()
status = client.map_key_status()
sources = client.data_availability("ALL")
recent_world = client.area("VIIRS_SNPP_NRT", "world", 1)
historical_bbox = client.area("VIIRS_SNPP_NRT", (-124.6, 32, -114.1312, 42.01), 3, "2026-03-01")
peru = client.country("MODIS_NRT", "PER", 4)
```

## Practical Notes For Another AI

- Prefer `requests.Session` so repeated calls reuse connections.
- Treat `data_availability("ALL")` as the canonical source catalog.
- Keep `DATE` optional for `area` and likely optional for `country`.
- Optional constant classes are useful for common strings, but the client should not require them.
- `ok()` should be a non-raising connectivity check, while `remaining()` should be a strict helper built from `map_key_status()`.
- Return CSV endpoints as pandas DataFrames, not raw text.
- Return KML/KMZ as bytes.
- Do not assume `countries` output format without testing; preserve passthrough behavior there.
- Do not hardcode sample dates from this directory into the client.
- Expect large CSV responses for world queries and design accordingly.

## Local Files That Back This Document

- `Firms Client.md`
- `samples/firms.modaps.eosdis.nasa.gov.json`
- `samples/data_availability-all.csv`
- `samples/data_availability-VIRRS_NOAA20_NRT.csv`
- `samples/area-sample-world.csv`
- `samples/area-sample-coords.csv`
- `samples/FirespotArea_SUOMI_VIIRS_C2_Alaska_24h.kmz`
- `tests/firms_api_use.ipynb`
