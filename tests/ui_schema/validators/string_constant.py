"""Validator for the `string_constant` block UI element."""

from jsonschema import ValidationError, validate


def validate_string_constant(schema: dict, param: str, ref: str) -> None:
    # Make sure type
    if schema.get("type") != "string":
        msg = f"Validation error at {ref}: string_constant param {param} should be of type 'string'"
        raise ValidationError(msg) from None

    const_value = schema.get("const")

    # Make sure const field exists
    if const_value is None:
        msg = (
            f"Validation error at {ref}: string_constant param {param} should "
            "have a 'const' field in its schema"
        )
        raise ValidationError(msg) from None

    # Make sure const is a string
    if not isinstance(const_value, str):
        msg = (
            f"Validation error at {ref}: string_constant param {param} should "
            "have a string as its 'const' field"
        )
        raise ValidationError(msg) from None

    # Try validating the constant value
    try:
        validate(const_value, schema)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: string_constant param {param} failed to validate a string"
        )
        raise ValidationError(msg) from None
