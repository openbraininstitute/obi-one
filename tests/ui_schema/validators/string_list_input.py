"""Validator for the `string_list_input` block UI element."""

from jsonschema import ValidationError

from .shared import accepts


def validate_string_list_param(schema: dict, param: str, ref: str) -> None:
    # Must accept a list of strings and reject anything else.
    if not accepts(schema, ["a"]) or any(
        accepts(schema, rejected) for rejected in ("a", None, [1])
    ):
        msg = (
            f"Validation error at {ref}: string_list_input param {param} should validate a "
            f"list of strings and nothing else"
        )
        raise ValidationError(msg) from None
