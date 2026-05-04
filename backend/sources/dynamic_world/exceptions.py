class DynamicWorldError(Exception):
    pass


class DynamicWorldAuthenticationError(DynamicWorldError):
    pass


class DynamicWorldInvalidCoordinatesError(DynamicWorldError):
    pass


class DynamicWorldInvalidDateError(DynamicWorldError):
    pass


class DynamicWorldEmptyBatchError(DynamicWorldError):
    pass
