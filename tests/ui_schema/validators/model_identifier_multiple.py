"""Validator for the `model_identifier_multiple` block UI element."""

from jsonschema import Draft7Validator, ValidationError

from .shared import get_ref_resolver, openapi_schema


def validate_model_identifier_multiple(schema: dict, param: str, ref: str) -> None:
    obj = {"id_str": "model_id"}

    items_schema = schema.get("items", {})
    validator = Draft7Validator(items_schema, resolver=get_ref_resolver(openapi_schema))

    try:
        validator.validate(obj)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: 'model_identifier_multiple' param {param} failed to "
            f"validate a 'model identifier' object {obj}"
        )
        raise ValidationError(msg) from None
