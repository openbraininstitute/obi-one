"""Validator for the `etype_selector` block UI element."""

from jsonschema import Draft7Validator, RefResolver, ValidationError

from obi_one.core.schema import SchemaKey

from .shared import openapi_schema


def validate_etype_selector(schema: dict, param: str, ref: str) -> None:
    """Validate an ETypeClass (Identifiable, not Entity) single-selector field.

    The field is an identifier reference (an ``{"id_str": ...}`` object) and must declare an
    ``entity_query`` of ``{"type": "etype"}``.
    """
    entity_query = schema.get(SchemaKey.ENTITY_QUERY)
    if not isinstance(entity_query, dict) or entity_query.get("type") != "etype":
        msg = (
            f"Validation error at {ref}: etype_selector param {param} must declare an "
            f"'{SchemaKey.ENTITY_QUERY}' of {{'type': 'etype'}}. Got: {entity_query!r}"
        )
        raise ValidationError(msg) from None

    resolver = RefResolver.from_schema(openapi_schema)
    validator = Draft7Validator(schema, resolver=resolver)

    obj = {"id_str": "etype_id"}
    try:
        validator.validate(obj)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: 'etype_selector' param {param} failed to validate "
            f"an etype identifier object {obj}"
        )
        raise ValidationError(msg) from None
