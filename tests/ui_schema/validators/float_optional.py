"""Validator for the `float_optional` block UI element."""

from jsonschema import ValidationError, validate

from .shared import determine_minimum_valid_numeric_value


def validate_float_optional(schema: dict, param: str, ref: str) -> None:
    any_of = schema.get("anyOf", [{}, {}])
    if any_of[0].get("type") != "number":
        msg = (
            f"Validation error at {ref}: float_optional param {param} should "
            "be a union with a 'number' as first element"
        )
        raise ValidationError(msg) from None

    if any_of[1].get("type") != "null":
        msg = (
            f"Validation error at {ref}: float_optional param {param} should "
            "be a union with 'null' as second element"
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
