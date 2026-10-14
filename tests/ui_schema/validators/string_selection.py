"""Validator for the `string_selection` block UI element."""

from jsonschema import ValidationError, validate


def validate_string_selection(schema: dict, param: str, ref: str) -> None:
    # Make sure type
    if schema.get("type") != "string":
        msg = (
            f"Validation error at {ref}: string_dropdown param {param} should "
            "be a union with a 'string' as first element"
        )
        raise ValidationError(msg) from None

    enum_list = schema.get("enum")

    # Make sure enum field exists
    if enum_list is None:
        msg = (
            f"Validation error at {ref}: string_dropdown param {param} should "
            "have an 'enum' field in its schema"
        )
        raise ValidationError(msg) from None

    # Make sure enum is a non-empty list
    if type(enum_list) is not list or len(enum_list) == 0:
        msg = (
            f"Validation error at {ref}: string_dropdown param {param} should "
            "have a non-empty list as its 'enum' field"
        )
        raise ValidationError(msg) from None

    # Make sure all the values in the enum are strings
    if not all(isinstance(val, str) for val in enum_list):
        msg = (
            f"Validation error at {ref}: string_dropdown param {param} has "
            "an enum value that is not a string"
        )
        raise ValidationError(msg) from None

    # Try validating a single string value
    try:
        validate(enum_list[0], schema)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: string_dropdown param {param} failed to validate a string"
        )
        raise ValidationError(msg) from None
