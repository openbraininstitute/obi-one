"""Validator for the `entity_property_multi_select` block UI element."""

from jsonschema import ValidationError

from obi_one.core.schema import SchemaKey

from .shared import accepts, validate_string


def validate_entity_property_multi_select(schema: dict, param: str, ref: str) -> None:
    validate_string(schema, SchemaKey.PROPERTY_GROUP, f"{param} at {ref}")
    validate_string(schema, SchemaKey.PROPERTY, f"{param} at {ref}")

    # One list value (not a parameter sweep): must accept a list of strings and reject
    # a single string, null and non-string items.
    if not accepts(schema, ["a"]) or any(
        accepts(schema, rejected) for rejected in ("a", None, [1])
    ):
        msg = (
            f"Validation error at {ref}: entity_property_multi_select param {param} should"
            " validate a list of strings and nothing else"
        )
        raise ValidationError(msg) from None
