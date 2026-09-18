"""Validator for the `model_identifier_multiple` block UI element."""

from jsonschema import Draft7Validator, RefResolver, ValidationError

from .shared import openapi_schema


def validate_model_identifier_multiple(schema: dict, param: str, ref: str) -> None:
    resolver = RefResolver.from_schema(openapi_schema)

    obj = {"id_str": "model_id"}

    items_schema = schema.get("items", {})
    validator = Draft7Validator(items_schema, resolver=resolver)

    try:
        validator.validate(obj)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: 'model_identifier_multiple' param {param} failed to "
            f"validate a 'model identifier' object {obj}"
        )
        raise ValidationError(msg) from None
