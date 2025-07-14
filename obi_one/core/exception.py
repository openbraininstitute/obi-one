class OBIONE_Error(Exception):
    """Base exception class for OBI-ONE."""


class ConfigValidationError(OBIONE_Error):
    """Exception raised for validation errors in OBI-ONE."""

class ProtocolNotFoundError(Exception):
    def __init__(self, missing_protocols: list[str]):
        self.missing_protocols = missing_protocols
        message = (
            f"None of the requested protocols were found in the data: {missing_protocols}"
        )
        super().__init__(message)