"""Validator for the `int_list_optional` block UI element."""

from jsonschema import ValidationError

from .shared import accepts


def validate_int_list_optional(schema: dict, param: str, ref: str) -> None:
    # Must accept a list of integers and null, and reject anything else.
    if (
        not accepts(schema, [1])
        or not accepts(schema, None)
        or any(accepts(schema, rejected) for rejected in (1, ["a"], [1.5]))
    ):
        msg = (
            f"Validation error at {ref}: int_list_optional param {param} should validate a "
            "list of integers or null and nothing else"
        )
        raise ValidationError(msg) from None
