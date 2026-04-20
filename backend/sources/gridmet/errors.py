class GridMETError(Exception):
    """Base exception for GridMET client errors."""


class GridMETDownloadError(GridMETError):
    """Raised when a remote GridMET file cannot be located or downloaded."""


class GridMETDataError(GridMETError):
    """Raised when a GridMET NetCDF file is unreadable or has an invalid schema."""


class GridMETCacheError(GridMETError):
    """Raised when client-owned cache management fails."""
