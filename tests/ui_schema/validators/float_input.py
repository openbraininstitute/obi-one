"""Validator for the `float_input` block UI element."""

from jsonschema import ValidationError

from .shared import accepts


def validate_float_input(schema: dict, param: str, ref: str) -> None:
    # Must accept a single number and reject anything else (null, string, list).
    # Use the schema's own default as the "valid number" sample so bounds are respected.
    valid_number = schema.get("default", schema.get("minimum", 0.0))
    if not accepts(schema, valid_number) or any(
        accepts(schema, rejected) for rejected in (None, "a", [1.0])
    ):
        msg = (
            f"Validation error at {ref}: float_input param {param} should validate a "
            f"single number and nothing else"
        )
        raise ValidationError(msg) from None
