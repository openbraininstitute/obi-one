"""Validator for the `string_selection_enhanced` block UI element."""

from .shared import validate_enhanced_string_fields
from .string_selection import validate_string_selection


def validate_string_selection_enhanced(schema: dict, param: str, ref: str) -> None:
    validate_string_selection(schema=schema, param=param, ref=ref)

    enum_list = schema.get("enum")
    validate_enhanced_string_fields(schema=schema, param=param, ref=ref, enum_list=enum_list)
