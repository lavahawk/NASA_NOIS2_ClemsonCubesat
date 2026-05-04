from __future__ import annotations

import contextlib
import datetime as dt
import calendar
import re
import tempfile
from numbers import Real
from pathlib import Path
from typing import Any

import requests
import xarray as xr

from .cache import CacheManager
from .errors import GridMETCacheError, GridMETDataError, GridMETDownloadError

class GridMETClient:
    """Client for point lookups against yearly GridMET NetCDF files."""

    _DATASET_RE = re.compile(r"^[A-Za-z0-9_]+$")
    _MIN_YEAR = 1979

    def __init__(
        self,
        base_url: str = "https://www.northwestknowledge.net/metdata/data",
        *,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()
        self._cache = CacheManager()
        self._active_dataset: xr.Dataset | None = None
        self._active_dataset_name: str | None = None
        self._active_year: int | None = None
        self._active_variable: str | None = None
        self._freshness: dict[tuple[str, int], tuple[str, str] | None] = {}

    def sel(
        self,
        dataset: str,
        lat: float,
        lon: float,
        year: int | None = None,
        day: int | None = None,
    ) -> float:
        dataset_name = self._validate_dataset(dataset)
        lat_value, lon_value = self._validate_coordinates(lat, lon)

        if year is None and day is None:
            year = self._ensure_latest_available_year(dataset_name)
            self._ensure_loaded(dataset_name, year)
            return self._select_latest_value(lat_value, lon_value)

        year_value, day_value = self._validate_year_day(year, day)
        target_date = self._date_from_year_day(year_value, day_value)
        self._ensure_year_available(dataset_name, year_value)
        self._ensure_loaded(dataset_name, year_value)
        return self._select_dated_value(lat_value, lon_value, target_date)

    def refresh_latest(self, dataset: str) -> None:
        dataset_name = self._validate_dataset(dataset)
        current_year = dt.date.today().year
        head_response = self._head_year(dataset_name, current_year, missing_ok=True)

        if head_response is None:
            fallback_year = self._ensure_latest_available_year(dataset_name, start_year=current_year - 1)
            if self._active_dataset_name == dataset_name and self._active_year == fallback_year:
                self._ensure_loaded(dataset_name, fallback_year, force_reload=True)
            return

        signal = self._extract_freshness_signal(head_response)
        head_response.close()
        cache_path = self._cache.file_path(dataset_name, current_year)
        known_signal = self._freshness.get((dataset_name, current_year))
        needs_download = not cache_path.exists() or signal is None or known_signal != signal

        if needs_download:
            self._download_to_cache(dataset_name, current_year, signal=signal)
            if self._active_dataset_name == dataset_name and self._active_year == current_year:
                self._ensure_loaded(dataset_name, current_year, force_reload=True)
        elif self._active_dataset_name == dataset_name and self._active_year == current_year and self._active_dataset is None:
            self._ensure_loaded(dataset_name, current_year)

    def clear_cache(self, start_year: int | None = None, end_year: int | None = None) -> None:
        if self._active_year is not None:
            in_range = True
            if start_year is not None and self._active_year < start_year:
                in_range = False
            if end_year is not None and self._active_year > end_year:
                in_range = False
            if in_range:
                self._close_active_dataset()

        keys_to_remove = [
            (dataset, year)
            for dataset, year in self._freshness
            if (start_year is None or year >= start_year) and (end_year is None or year <= end_year)
        ]
        for key in keys_to_remove:
            self._freshness.pop(key, None)

        self._cache.clear_cache(start_year, end_year)

    @property
    def cache_root(self) -> Path:
        """Return the client-owned cache root, creating it if needed."""
        return self._cache.root

    @property
    def cache_root_if_present(self) -> Path | None:
        """Return the existing client-owned cache root without creating one."""
        return self._cache.root_if_present

    def cache_path(self, dataset: str, year: int) -> Path:
        """Return the on-disk cache path for a dataset-year pair."""
        dataset_name = self._validate_dataset(dataset)
        if not isinstance(year, int) or isinstance(year, bool):
            raise ValueError("year must be an integer.")
        return self._cache.file_path(dataset_name, year)

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self._close_active_dataset()
        with contextlib.suppress(Exception):
            self._cache.clear_cache()

    def _validate_dataset(self, dataset: str) -> str:
        if not isinstance(dataset, str) or not dataset:
            raise ValueError("dataset must be a non-empty string.")
        if not self._DATASET_RE.fullmatch(dataset):
            raise ValueError("dataset must match the pattern '^[A-Za-z0-9_]+$'.")
        return dataset

    def _validate_coordinates(self, lat: float, lon: float) -> tuple[float, float]:
        if not isinstance(lat, Real) or isinstance(lat, bool):
            raise ValueError("lat must be numeric.")
        if not isinstance(lon, Real) or isinstance(lon, bool):
            raise ValueError("lon must be numeric.")
        lat_value = float(lat)
        lon_value = float(lon)
        if not -90.0 <= lat_value <= 90.0:
            raise ValueError("lat must be within [-90, 90].")
        if not -180.0 <= lon_value <= 180.0:
            raise ValueError("lon must be within [-180, 180].")
        return lat_value, lon_value

    def _validate_year_day(self, year: int | None, day: int | None) -> tuple[int, int]:
        if (year is None) != (day is None):
            raise ValueError("year and day must be provided together for explicit-date selection.")
        if not isinstance(year, int) or isinstance(year, bool):
            raise ValueError("year must be an integer.")
        if not isinstance(day, int) or isinstance(day, bool):
            raise ValueError("day must be an integer day-of-year.")

        date_value = dt.date(year, 1, 1)
        current_year = dt.date.today().year
        if date_value.year > current_year:
            raise ValueError("year cannot exceed the current calendar year.")
        if date_value.year < self._MIN_YEAR:
            raise ValueError(f"year must be at least {self._MIN_YEAR}.")

        max_day = 366 if calendar.isleap(year) else 365
        if not 1 <= day <= max_day:
            raise ValueError(f"day must be within [1, {max_day}] for year {year}.")

        return year, day

    def _date_from_year_day(self, year: int, day: int) -> dt.date:
        return dt.date(year, 1, 1) + dt.timedelta(days=day - 1)

    def _build_url(self, dataset: str, year: int) -> str:
        return f"{self.base_url}/{dataset}_{year}.nc"

    def _ensure_year_available(self, dataset: str, year: int) -> Path:
        if year < self._MIN_YEAR:
            raise GridMETDownloadError(f"No GridMET file found for dataset '{dataset}' at or after {self._MIN_YEAR}.")
        cache_path = self._cache.file_path(dataset, year)
        if cache_path.exists():
            return cache_path
        return self._download_to_cache(dataset, year)

    def _ensure_latest_available_year(self, dataset: str, start_year: int | None = None) -> int:
        year = start_year or dt.date.today().year
        current_year_path = self._cache.file_path(dataset, year)
        if start_year is None and current_year_path.exists():
            return year

        for candidate_year in range(year, self._MIN_YEAR - 1, -1):
            candidate_path = self._cache.file_path(dataset, candidate_year)
            if candidate_path.exists():
                return candidate_year
            try:
                self._download_to_cache(dataset, candidate_year)
                return candidate_year
            except GridMETDownloadError:
                continue

        raise GridMETDownloadError(
            f"No GridMET file found for dataset '{dataset}' from {year} back through {self._MIN_YEAR}."
        )

    def _head_year(self, dataset: str, year: int, *, missing_ok: bool) -> requests.Response | None:
        url = self._build_url(dataset, year)
        try:
            response = self._session.head(url, allow_redirects=True, timeout=self.timeout)
        except requests.RequestException as exc:
            raise GridMETDownloadError(f"HEAD request failed for '{url}'.") from exc
        if response.status_code == 404 and missing_ok:
            return None
        if response.status_code >= 400:
            raise GridMETDownloadError(
                f"HEAD request for '{url}' returned unexpected status {response.status_code}."
            )
        return response

    def _extract_freshness_signal(self, response: requests.Response) -> tuple[str, str] | None:
        etag = response.headers.get("ETag")
        if etag:
            return ("etag", etag)
        last_modified = response.headers.get("Last-Modified")
        if last_modified:
            return ("last-modified", last_modified)
        content_length = response.headers.get("Content-Length")
        if content_length:
            return ("content-length", content_length)
        return None

    def _download_to_cache(
        self,
        dataset: str,
        year: int,
        *,
        signal: tuple[str, str] | None = None,
    ) -> Path:
        url = self._build_url(dataset, year)
        destination = self._cache.file_path(dataset, year)

        temp_file = None
        temp_path: Path | None = None
        try:
            with self._session.get(url, stream=True, timeout=self.timeout) as response:
                if response.status_code == 404:
                    raise GridMETDownloadError(f"GridMET file not found: '{url}'.")
                if response.status_code >= 400:
                    raise GridMETDownloadError(f"Download failed for '{url}' with status {response.status_code}.")

                temp_file = tempfile.NamedTemporaryFile(
                    mode="wb",
                    suffix=".part",
                    prefix=f"{dataset}_{year}_",
                    dir=str(destination.parent),
                    delete=False,
                )
                temp_path = Path(temp_file.name)
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        temp_file.write(chunk)
                temp_file.flush()
        except GridMETCacheError:
            raise
        except requests.RequestException as exc:
            raise GridMETDownloadError(f"Download request failed for '{url}'.") from exc
        except OSError as exc:
            raise GridMETCacheError(f"Failed to write temporary cache file for dataset '{dataset}' year {year}.") from exc
        finally:
            if temp_file is not None:
                with contextlib.suppress(Exception):
                    temp_file.close()

        if temp_path is None or not temp_path.exists():
            raise GridMETCacheError(f"Failed to stage downloaded file for dataset '{dataset}' year {year}.")

        try:
            self._cache.replace_file(destination, temp_path)
        finally:
            if temp_path.exists():
                with contextlib.suppress(OSError):
                    temp_path.unlink()

        if signal is None:
            try:
                head_response = self._head_year(dataset, year, missing_ok=False)
            except GridMETDownloadError:
                signal = None
            else:
                signal = self._extract_freshness_signal(head_response)
                head_response.close()
        self._freshness[(dataset, year)] = signal
        return destination

    def _ensure_loaded(self, dataset: str, year: int, *, force_reload: bool = False) -> None:
        if (
            not force_reload
            and self._active_dataset is not None
            and self._active_dataset_name == dataset
            and self._active_year == year
        ):
            return

        path = self._ensure_year_available(dataset, year)
        self._close_active_dataset()
        ds: xr.Dataset | None = None
        try:
            ds = xr.open_dataset(path)
            variable_name = self._get_primary_variable(ds)
        except (OSError, ValueError) as exc:
            raise GridMETDataError(f"Failed to open NetCDF dataset '{path}'.") from exc
        except GridMETDataError:
            if ds is not None:
                with contextlib.suppress(Exception):
                    ds.close()
            raise

        self._active_dataset = ds
        self._active_dataset_name = dataset
        self._active_year = year
        self._active_variable = variable_name

    def _close_active_dataset(self) -> None:
        if self._active_dataset is not None:
            with contextlib.suppress(Exception):
                self._active_dataset.close()
        self._active_dataset = None
        self._active_dataset_name = None
        self._active_year = None
        self._active_variable = None

    def _get_primary_variable(self, ds: xr.Dataset) -> str:
        required_coords = {"day", "lat", "lon"}
        if not required_coords.issubset(ds.coords):
            missing = ", ".join(sorted(required_coords - set(ds.coords)))
            raise GridMETDataError(f"Dataset is missing required coordinates: {missing}.")

        candidates = [
            name
            for name, data_array in ds.data_vars.items()
            if tuple(data_array.dims) == ("day", "lat", "lon")
        ]
        if not candidates:
            raise GridMETDataError("No primary data variable with dimensions ('day', 'lat', 'lon') was found.")
        if len(candidates) > 1:
            raise GridMETDataError(
                "Multiple candidate primary data variables with dimensions ('day', 'lat', 'lon') were found."
            )
        return candidates[0]

    def _select_dated_value(self, lat: float, lon: float, target_date: dt.date) -> float:
        ds = self._require_active_dataset()
        variable_name = self._require_active_variable()
        try:
            day_selected = ds[variable_name].sel(day=target_date.isoformat())
            selected = day_selected.sel(lat=lat, lon=lon, method="nearest")
        except KeyError as exc:
            raise GridMETDataError(f"Requested date {target_date.isoformat()} is not present in the dataset.") from exc
        except Exception as exc:
            raise GridMETDataError("Failed to resolve the requested GridMET point selection.") from exc
        return self._to_python_scalar(selected.values)

    def _select_latest_value(self, lat: float, lon: float) -> float:
        ds = self._require_active_dataset()
        variable_name = self._require_active_variable()
        try:
            selected = ds[variable_name].isel(day=-1).sel(lat=lat, lon=lon, method="nearest")
        except Exception as exc:
            raise GridMETDataError("Failed to resolve the requested latest GridMET point selection.") from exc
        return self._to_python_scalar(selected.values)

    def _require_active_dataset(self) -> xr.Dataset:
        if self._active_dataset is None:
            raise GridMETDataError("No active dataset is loaded.")
        return self._active_dataset

    def _require_active_variable(self) -> str:
        if self._active_variable is None:
            raise GridMETDataError("No active primary variable is loaded.")
        return self._active_variable

    def _to_python_scalar(self, value: Any) -> float:
        try:
            scalar = value.item()
        except AttributeError:
            scalar = value
        if isinstance(scalar, bool) or not isinstance(scalar, Real):
            raise GridMETDataError(f"Selected value is not numeric: {scalar!r}.")
        return float(scalar)
