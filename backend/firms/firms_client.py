from __future__ import annotations

import datetime as dt
import io
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import requests

__all__ = [
    "FirmsClient",
    "FirmsDateSpan",
    "FirmsError",
    "FirmsFootprintSensor",
    "FirmsHTTPError",
    "FirmsRegion",
    "FirmsSource",
    "FirmsValidationError",
]


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


CSVFrame = pd.DataFrame
AreaInput = str | tuple[float, float, float, float] | list[float]
DateInput = str | dt.date


@dataclass(slots=True)
class FirmsClient:
    map_key: str
    base_url: str = "https://firms.modaps.eosdis.nasa.gov"
    timeout: float = 30.0
    session: requests.Session = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.map_key, str) or not self.map_key.strip():
            raise FirmsValidationError("map_key must be a non-empty string")
        if not isinstance(self.base_url, str) or not self.base_url.strip():
            raise FirmsValidationError("base_url must be a non-empty string")
        if not isinstance(self.timeout, (int, float)) or self.timeout <= 0:
            raise FirmsValidationError("timeout must be a positive number")
        self.map_key = self.map_key.strip()
        self.base_url = self.base_url.rstrip("/")
        self.timeout = float(self.timeout)
        # Reuse a session so repeated FIRMS calls share connection state.
        self.session = requests.Session()

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
            raise FirmsHTTPError(
                "map_key_status response did not include usable transaction counters"
            ) from exc
        return max(0, limit - used)

    def map_key_status(self) -> dict[str, Any]:
        return self._get_json(
            "/mapserver/mapkey_status/",
            params={"MAP_KEY": self.map_key},
        )

    def data_availability(self, source: str = "ALL") -> CSVFrame:
        source_value = self._require_non_empty_string(source, "source")
        return self._get_csv_frame(f"/api/data_availability/csv/{self.map_key}/{source_value}")

    def area(
        self,
        source: str,
        area: AreaInput,
        day_range: int,
        date: DateInput | None = None,
    ) -> CSVFrame:
        source_value = self._require_non_empty_string(source, "source")
        # Accept either the literal "world" or a west,south,east,north bounding box.
        area_value = self._normalize_area(area)
        day_range_value = self._validate_day_range(day_range)
        path = f"/api/area/csv/{self.map_key}/{source_value}/{area_value}/{day_range_value}"
        if date is not None:
            path = f"{path}/{self._normalize_date(date)}"
        return self._get_csv_frame(path)

    def countries(self, format: str | None = None) -> str:
        params = None
        if format is not None:
            params = {"format": self._require_non_empty_string(format, "format")}
        response = self._request("/api/countries", params=params)
        return response.text

    def country(
        self,
        source: str,
        country_code: str,
        day_range: int,
        date: DateInput | None = None,
    ) -> CSVFrame:
        source_value = self._require_non_empty_string(source, "source")
        country_value = self._normalize_country_code(country_code)
        day_range_value = self._validate_day_range(day_range)
        path = f"/api/country/csv/{self.map_key}/{source_value}/{country_value}/{day_range_value}"
        if date is not None:
            path = f"{path}/{self._normalize_date(date)}"
        return self._get_csv_frame(path)

    def kml_fire_footprints(self, region: str, date_span: str, sensor: str) -> bytes:
        region_value = self._require_non_empty_string(region, "region")
        date_span_value = self._require_non_empty_string(date_span, "date_span")
        sensor_value = self._require_non_empty_string(sensor, "sensor")
        response = self._request(
            f"/api/kml_fire_footprints/{region_value}/{date_span_value}/{sensor_value}"
        )
        return response.content

    def _normalize_date(self, value: DateInput) -> str:
        if isinstance(value, dt.date):
            return value.isoformat()
        if not isinstance(value, str):
            raise FirmsValidationError("date must be a datetime.date or YYYY-MM-DD string")
        try:
            return dt.date.fromisoformat(value).isoformat()
        except ValueError as exc:
            raise FirmsValidationError(f"invalid date: {value!r}") from exc

    def _validate_day_range(self, value: int) -> int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise FirmsValidationError("day_range must be an integer between 1 and 5")
        if not 1 <= value <= 5:
            raise FirmsValidationError("day_range must be an integer between 1 and 5")
        return value

    def _normalize_area(self, value: AreaInput) -> str:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "world":
                return "world"
            parts = [part.strip() for part in stripped.split(",")]
            if len(parts) != 4:
                raise FirmsValidationError("area string must be 'west,south,east,north'")
            try:
                coords = tuple(float(part) for part in parts)
            except ValueError as exc:
                raise FirmsValidationError("area coordinates must be numeric") from exc
        elif isinstance(value, (tuple, list)):
            if len(value) != 4:
                raise FirmsValidationError("area tuple must have four values")
            try:
                coords = tuple(float(part) for part in value)
            except (TypeError, ValueError) as exc:
                raise FirmsValidationError("area coordinates must be numeric") from exc
        else:
            raise FirmsValidationError(
                "area must be 'world' or a 4-value bounding box"
            )

        west, south, east, north = coords
        if west < -180 or east > 180 or south < -90 or north > 90:
            raise FirmsValidationError("area is outside valid world bounds")
        if west >= east or south >= north:
            raise FirmsValidationError("area bounds must satisfy west < east and south < north")
        # Keep the final path segment compact and stable for URL construction.
        return f"{west:g},{south:g},{east:g},{north:g}"

    def _normalize_country_code(self, country_code: str) -> str:
        code = self._require_non_empty_string(country_code, "country_code").upper()
        if len(code) != 3:
            raise FirmsValidationError("country_code must be a 3-letter code")
        return code

    def _require_non_empty_string(self, value: str, name: str) -> str:
        if not isinstance(value, str):
            raise FirmsValidationError(f"{name} must be a non-empty string")
        stripped = value.strip()
        if not stripped:
            raise FirmsValidationError(f"{name} must be a non-empty string")
        return stripped

    def _request(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> requests.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise FirmsHTTPError(f"request failed for {url}: {exc}") from exc
        # Normalize all HTTP failures into the client-specific exception type.
        self._raise_for_status(response)
        return response

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._request(path, params=params)
        try:
            data = response.json()
        except ValueError as exc:
            raise FirmsHTTPError(f"invalid JSON returned for {response.url}") from exc
        if not isinstance(data, dict):
            raise FirmsHTTPError(f"expected JSON object from {response.url}")
        return data

    def _get_csv_frame(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> CSVFrame:
        response = self._request(path, params=params)
        return self._parse_csv_frame(response.text)

    def _parse_csv_frame(self, text: str) -> CSVFrame:
        # The notebooks in this workspace use DataFrames as the main interface for FIRMS CSV data.
        return pd.read_csv(io.StringIO(text))

    def _raise_for_status(self, response: requests.Response) -> None:
        if response.ok:
            return
        snippet = response.text[:500] if response.text else ""
        raise FirmsHTTPError(f"{response.status_code} for {response.url}: {snippet}")
