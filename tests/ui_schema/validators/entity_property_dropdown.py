"""Validator for the `entity_property_dropdown` block UI element."""

from jsonschema import ValidationError

from obi_one.core.schema import SchemaKey

from .shared import validate_string, validate_string_param


def validate_entity_property_dropdown(schema: dict, param: str, ref: str) -> None:
    validate_string(schema, SchemaKey.PROPERTY_GROUP, f"{param} at {ref}")
    validate_string(schema, SchemaKey.PROPERTY, f"{param} at {ref}")

    try:
        validate_string_param(schema, param, ref)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: entity_property_dropdown param {param} failed"
            "to validate a string"
        )
        raise ValidationError(msg) from None
