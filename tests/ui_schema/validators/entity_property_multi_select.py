"""Validator for the `entity_property_multi_select` block UI element."""

from jsonschema import ValidationError

from obi_one.core.schema import SchemaKey

from .shared import accepts, validate_string


def validate_entity_property_multi_select(schema: dict, param: str, ref: str) -> None:
    validate_string(schema, SchemaKey.PROPERTY_GROUP, f"{param} at {ref}")
    validate_string(schema, SchemaKey.PROPERTY, f"{param} at {ref}")

    # Must accept a list of strings, which may be empty, and reject anything else.
    if (
        not accepts(schema, ["a"])
        or not accepts(schema, [])
        or any(accepts(schema, rejected) for rejected in ("a", None, [1]))
    ):
        msg = (
            f"Validation error at {ref}: entity_property_multi_select param {param} should "
            "validate a list of strings, which may be empty, and nothing else"
        )
        raise ValidationError(msg) from None
