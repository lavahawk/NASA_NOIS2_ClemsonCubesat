from __future__ import annotations


class QueryValidationError(Exception):
    def __init__(self, message: str, *, parameter: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.parameter = parameter


class DatabaseUnavailableError(Exception):
    pass
