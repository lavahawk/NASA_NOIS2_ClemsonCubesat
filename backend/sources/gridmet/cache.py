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

    def clear(self) -> None:
        root = self._root
        self._root = None
        if root is None:
            return
        try:
            if root.exists():
                shutil.rmtree(root)
        except OSError as exc:
            raise GridMETCacheError(f"Failed to remove cache root '{root}'.") from exc

    def _ensure_root(self) -> Path:
        if self._root is not None:
            return self._root
        try:
            self._root = Path.cwd() / f"{self._prefix}{uuid.uuid4().hex}"
            self._root.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise GridMETCacheError("Failed to create a temporary GridMET cache directory.") from exc
        return self._root
