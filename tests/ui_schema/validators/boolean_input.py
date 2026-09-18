"""Validator for the `boolean_input` block UI element."""

from jsonschema import ValidationError, validate


def validate_boolean_input(schema: dict, param: str, ref: str) -> None:
    if schema.get("type") != "boolean":
        msg = f"Validation error at {ref}: boolean_input param {param} should have type 'boolean'"
        raise ValidationError(msg)

    test_true = True
    test_false = False

    try:
        validate(test_true, schema)
    except ValidationError:
        msg = f"Validation error at {ref}: boolean_input param {param} failed to validate True"
        raise ValidationError(msg) from None

    try:
        validate(test_false, schema)
    except ValidationError:
        msg = f"Validation error at {ref}: boolean_input param {param} failed to validate False"
        raise ValidationError(msg) from None
