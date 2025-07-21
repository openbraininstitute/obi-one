class OBIONEError(Exception):
    """Base exception class for OBI-ONE."""


class ConfigValidationError(OBIONEError):
    """Exception raised for validation errors in OBI-ONE."""
