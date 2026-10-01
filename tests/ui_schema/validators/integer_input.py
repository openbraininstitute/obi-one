"""Validator for the `integer_input` block UI element."""

from jsonschema import ValidationError

from .shared import accepts


def validate_integer_input(schema: dict, param: str, ref: str) -> None:
    # Must accept a single integer and reject anything else (null, float, string, list).
    # Use the schema's own default as the "valid integer" sample so bounds are respected.
    valid_integer = schema.get("default", schema.get("minimum", 0))
    if not accepts(schema, valid_integer) or any(
        accepts(schema, rejected) for rejected in (None, 1.5, "a", [1])
    ):
        msg = (
            f"Validation error at {ref}: integer_input param {param} should validate a "
            f"single integer and nothing else"
        )
        raise ValidationError(msg) from None
