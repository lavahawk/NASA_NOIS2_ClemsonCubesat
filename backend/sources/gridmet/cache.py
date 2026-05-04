from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from .errors import GridMETCacheError


class CacheManager:
    """Manages a client-owned temporary cache root."""

    def __init__(self, prefix: str = ".gridmet-", *, create_immediately: bool = True) -> None:
        self._prefix = prefix
        self._root: Path | None = None
        if create_immediately:
            self._ensure_root()

    @property
    def root(self) -> Path:
        return self._ensure_root()

    @property
    def root_if_present(self) -> Path | None:
        return self._root

    def dataset_dir(self, dataset: str) -> Path:
        path = self.root / dataset
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise GridMETCacheError(f"Failed to create cache directory for dataset '{dataset}'.") from exc
        return path

    def file_path(self, dataset: str, year: int) -> Path:
        return self.dataset_dir(dataset) / f"{dataset}_{year}.nc"

    def replace_file(self, destination: Path, source: Path) -> None:
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.replace(destination)
        except OSError as exc:
            raise GridMETCacheError(f"Failed to replace cached file '{destination}'.") from exc

    def clear_cache(self, start_year: int | None = None, end_year: int | None = None) -> None:
        root = self._root
        if root is None or not root.exists():
            self._root = None
            return

        if start_year is None and end_year is None:
            try:
                shutil.rmtree(root)
                self._root = None
            except OSError as exc:
                raise GridMETCacheError(f"Failed to remove cache root '{root}'.") from exc
            return

        try:
            for dataset_dir in root.iterdir():
                if not dataset_dir.is_dir():
                    continue
                
                for file_path in dataset_dir.glob("*.nc"):
                    # Extract year from filename, e.g., "fm1000_2026.nc"
                    parts = file_path.stem.split('_')
                    if len(parts) >= 2 and parts[-1].isdigit():
                        year = int(parts[-1])
                        in_range = True
                        if start_year is not None and year < start_year:
                            in_range = False
                        if end_year is not None and year > end_year:
                            in_range = False
                        
                        if in_range:
                            file_path.unlink()

                if not any(dataset_dir.iterdir()):
                    dataset_dir.rmdir()

            if not any(root.iterdir()):
                root.rmdir()
                self._root = None
        except OSError as exc:
            raise GridMETCacheError(f"Failed to selectively clear cache root '{root}'.") from exc

    def _ensure_root(self) -> Path:
        if self._root is not None:
            return self._root
        try:
            self._root = Path.cwd() / f"{self._prefix}{uuid.uuid4().hex}"
            self._root.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise GridMETCacheError("Failed to create a temporary GridMET cache directory.") from exc
        return self._root
