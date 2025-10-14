"""Api exceptions."""

import dataclasses
from enum import StrEnum
from http import HTTPStatus
from typing import Any


class AuthErrorReason(StrEnum):
    """Authentication and authorization errors."""

    AUTH_TOKEN_MISSING = "The authorization token is missing"  # noqa: S105
    AUTH_TOKEN_INVALID = "The authorization token is invalid"  # noqa: S105
    AUTH_TOKEN_EXPIRED = "The authorization token is expired"  # noqa: S105
    NOT_AUTHENTICATED_USER = "User not authenticated"
    NOT_AUTHORIZED_USER = "User not authorized"
    NOT_AUTHORIZED_PROJECT = "User not authorized for the given virtual-lab-id or project-id"
    PROJECT_REQUIRED = "The headers virtual-lab-id and project-id are required"
    ADMIN_REQUIRED = "Service admin role required"
    UNKNOWN = "Unknown reason"


class ApiErrorCode(StrEnum):
    """API Error codes."""

    GENERIC_ERROR = "GENERIC_ERROR"
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclasses.dataclass(kw_only=True)
class ApiError(Exception):
    """API Error."""

    message: str
    error_code: ApiErrorCode
    http_status_code: HTTPStatus | int = HTTPStatus.BAD_REQUEST
    details: Any = None

    def __repr__(self) -> str:
        """Return the repr of the error."""
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"error_code={self.error_code}, "
            f"http_status_code={self.http_status_code}, "
            f"details={self.details!r})"
        )

    def __str__(self) -> str:
        """Return the str representation."""
        return (
            f"message={self.message!r} "
            f"error_code={self.error_code} "
            f"http_status_code={self.http_status_code} "
            f"details={self.details!r}"
        )
