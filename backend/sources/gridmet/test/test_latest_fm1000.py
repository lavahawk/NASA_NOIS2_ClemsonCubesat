from __future__ import annotations

import shutil
from pathlib import Path

from gridmet import GridMETClient, GridMETDataset


def main() -> None:
    repo_root = Path(__file__).resolve().parent
    sample_path = repo_root / "samples" / "fm1000_2026.nc"

    client = GridMETClient(base_url="https://example.invalid")
    try:
        cache_root = client.cache_root
        cache_path = client.cache_path(GridMETDataset.FM1000, 2026)

        print(f"cache_root={cache_root}")
        print(f"cache_file={cache_path}")
        print(f"cache_file_exists_before_copy={cache_path.exists()}")

        shutil.copy2(sample_path, cache_path)
        print(f"cache_file_exists_after_copy={cache_path.exists()}")

        lat = 39.7392
        lon = -104.9903
        value = client.sel(GridMETDataset.FM1000, lat, lon)

        print(f"dataset={GridMETDataset.FM1000}")
        print(f"lat={lat}")
        print(f"lon={lon}")
        print(f"latest_value={value}")
    finally:
        old_root = client.cache_root_if_present
        client.clear()
        print(f"cache_root_after_clear={client.cache_root_if_present}")
        print(f"old_cache_root_exists_after_clear={old_root.exists() if old_root else False}")


if __name__ == "__main__":
    main()
