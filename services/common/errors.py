"""Errors any service may raise; apps/api/problems.py turns them into RFC 7807 responses."""


class InvalidInput(ValueError):
    """422: a request field is not acceptable (path is a JSON Pointer into the request body)."""

    def __init__(self, path: str, message: str):
        super().__init__(message)
        self.path, self.message = path, message


class Forbidden(PermissionError):
    """403 with a sentence the UI can show."""
