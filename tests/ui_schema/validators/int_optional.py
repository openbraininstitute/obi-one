"""Validator for the `int_optional` block UI element."""

from jsonschema import ValidationError

from .shared import accepts, determine_minimum_valid_numeric_value


def validate_int_optional(schema: dict, param: str, ref: str) -> None:
    # Must accept an integer and null, and reject anything else.
    any_of = schema.get("anyOf", [])
    if (
        not any_of
        or any_of[0].get("type") != "integer"
        or not accepts(schema, determine_minimum_valid_numeric_value(schema))
        or not accepts(schema, None)
        or any(accepts(schema, rejected) for rejected in ("a", 1.5, [1]))
    ):
        msg = (
            f"Validation error at {ref}: int_optional param {param} should validate an integer "
            "or null and nothing else"
        )
        raise ValidationError(msg) from None
