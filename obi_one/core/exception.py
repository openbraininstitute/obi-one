class OBIONEError(Exception):
    """Base exception class for OBI-ONE."""


class ConfigValidationError(OBIONEError):
    """Exception raised for validation errors in OBI-ONE."""


class ProtocolNotFoundError(Exception):
    def __init__(self, msg: list[str]) -> None:
        """Exception raised when a protocol is not found in the trace."""
        message = msg
        super().__init__(message)
