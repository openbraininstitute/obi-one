class OBIONEError(Exception):
    """Base exception class for OBI-ONE."""


class ConfigValidationError(OBIONEError, ValueError):
    """Exception raised for validation errors in OBI-ONE.

    Also a ValueError, so a check that already raised one can raise this without breaking callers
    that catch it.
    """


class ProtocolNotFoundError(Exception):
    def __init__(self, msg: list[str]) -> None:
        """Exception raised when a protocol is not found in the trace."""
        message = msg
        super().__init__(message)
