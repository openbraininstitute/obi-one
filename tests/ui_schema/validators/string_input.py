"""Validator for the `string_input` block UI element."""

from .shared import validate_string_param


def validate_string_input(schema: dict, param: str, ref: str) -> None:
    validate_string_param(schema, param, ref)
