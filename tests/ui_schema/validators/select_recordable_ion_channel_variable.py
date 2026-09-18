"""Validator for the `select_recordable_ion_channel_variable` block UI element."""

from obi_one.core.schema import SchemaKey

from .shared import validate_string


def validate_select_recordable_ion_channel_variable(schema: dict, param: str, ref: str) -> None:
    validate_string(schema, SchemaKey.PROPERTY_GROUP, f"{param} at {ref}")
    validate_string(schema, SchemaKey.PROPERTY, f"{param} at {ref}")
