class OBIONE_Error(Exception):
    """Base exception class for OBI-ONE."""


class ConfigValidationError(OBIONE_Error):
    """Exception raised for validation errors in OBI-ONE."""