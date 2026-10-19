"""Validator for the `string_list_optional` block UI element."""

from jsonschema import ValidationError

from .shared import accepts


def validate_string_list_optional(schema: dict, param: str, ref: str) -> None:
    # Must accept a list of strings and null, and reject anything else.
    if (
        not accepts(schema, ["a"])
        or not accepts(schema, None)
        or any(accepts(schema, rejected) for rejected in ("a", [1]))
    ):
        msg = (
            f"Validation error at {ref}: string_list_optional param {param} should validate a "
            f"list of strings or null and nothing else"
        )
        raise ValidationError(msg) from None
