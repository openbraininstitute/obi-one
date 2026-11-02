"""Validator for the `string_constant_enhanced` block UI element."""

from .shared import validate_enhanced_string_fields
from .string_constant import validate_string_constant


def validate_string_constant_enhanced(schema: dict, param: str, ref: str) -> None:
    validate_string_constant(schema=schema, param=param, ref=ref)

    enum_list = [schema.get("const")]
    validate_enhanced_string_fields(schema=schema, param=param, ref=ref, enum_list=enum_list)
