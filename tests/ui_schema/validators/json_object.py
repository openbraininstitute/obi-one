"""Validator for the `json_object` block UI element."""

from jsonschema import ValidationError

from .shared import accepts


def validate_json_object(schema: dict, param: str, ref: str) -> None:
    # Must accept any object, and reject anything else: its keys are free, unlike `object`'s.
    if (
        not accepts(schema, {})
        or not accepts(schema, {"a": [1, {"b": None}]})
        or any(accepts(schema, rejected) for rejected in ("a", 1, [1], None))
    ):
        msg = (
            f"Validation error at {ref}: json_object param {param} should validate any object "
            "and nothing else"
        )
        raise ValidationError(msg) from None
