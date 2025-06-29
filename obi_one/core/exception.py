class OBIONE_Error(Exception):
    """Base exception class for EntitySDK."""


class ConfigValidationError(OBIONE_Error):
    """Exception raised for validation errors in EntitySDK."""