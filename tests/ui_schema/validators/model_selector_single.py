"""Validator for the `model_selector_single` block UI element."""

from jsonschema import Draft7Validator, ValidationError

from obi_one.core.schema import SchemaKey

from .shared import openapi_resolver


def validate_model_selector_single(schema: dict, param: str, ref: str) -> None:
    """Validate a single-entity selector field.

    The field is a single ``FromID`` entity reference (an ``{"id_str": ...}`` object) that
    declares an ``entity_query`` with a ``type`` telling the frontend which entities to browse.
    """
    entity_query = schema.get(SchemaKey.ENTITY_QUERY)
    if not isinstance(entity_query, dict) or not entity_query.get("type"):
        msg = (
            f"Validation error at {ref}: model_selector_single param {param} must declare an "
            f"'{SchemaKey.ENTITY_QUERY}' with a 'type'. Got: {entity_query!r}"
        )
        raise ValidationError(msg)

    validator = Draft7Validator(schema, resolver=openapi_resolver)
    obj = {"id_str": "model_id"}
    try:
        validator.validate(obj)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: model_selector_single param {param} failed to validate "
            f"an entity-reference object {obj}"
        )
        raise ValidationError(msg) from None
