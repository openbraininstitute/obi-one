class OBIONE_Error(Exception):
    """Base exception class for OBI-ONE."""


class ConfigValidationError(OBIONE_Error):
    """Exception raised for validation errors in OBI-ONE."""

class ProtocolNotFoundError(Exception):
    def __init__(self, msg: list[str]):
        message = (msg)
        super().__init__(message)