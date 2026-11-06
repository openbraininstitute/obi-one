"""Validator for the `axon_modifier` block UI element."""

from .shared import (
    openapi_schema,
    resolve_ref,
    validate_enhanced_string_fields,
)
from .string_selection import validate_string_selection


def validate_axon_modifier(schema: dict, param: str, ref: str) -> None:
    # One-off element for the `axon_modifier` field, whose type is the `AxonModifier` enum
    # class. Pydantic emits enum-class fields as a `$ref` to a shared definition (unlike inline
    # `Literal` selections), so resolve the reference before applying the enhanced-selection
    # checks (enum + title_by_key + description_by_key keyed to the enum values).
    if schema.get("$ref"):
        schema = {**resolve_ref(openapi_schema, schema["$ref"]), **schema}
        schema.pop("$ref", None)

    validate_string_selection(schema=schema, param=param, ref=ref)

    enum_list = schema.get("enum")
    validate_enhanced_string_fields(schema=schema, param=param, ref=ref, enum_list=enum_list)
