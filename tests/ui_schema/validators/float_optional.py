"""Validator for the `float_optional` block UI element."""

from jsonschema import ValidationError, validate

from .shared import determine_minimum_valid_numeric_value


def validate_float_optional(schema: dict, param: str, ref: str) -> None:
    any_of = schema.get("anyOf", [])
    numeric_schema = next((branch for branch in any_of if branch.get("type") == "number"), None)
    if numeric_schema is None:
        msg = (
            f"Validation error at {ref}: float_optional param {param} should "
            "include a 'number' branch"
        )
        raise ValidationError(msg) from None

    if not any(branch.get("type") == "null" for branch in any_of):
        msg = (
            f"Validation error at {ref}: float_optional param {param} should include a null branch"
        )
        raise ValidationError(msg) from None

    test_value = determine_minimum_valid_numeric_value(schema)

    try:
        validate(test_value, schema)

    except ValidationError:
        msg = f"Validation error at {ref}: float_optional param {param} failed to validate a float"
        raise ValidationError(msg) from None

    try:
        validate(None, schema)

    except ValidationError:
        msg = (
            f"Validation error at {ref}: float_optional param {param} failed "
            "to validate a null value"
        )
        raise ValidationError(msg) from None
