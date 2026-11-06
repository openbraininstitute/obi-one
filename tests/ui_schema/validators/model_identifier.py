"""Validator for the `model_identifier` block UI element."""

from jsonschema import Draft7Validator, ValidationError

from .shared import get_ref_resolver, openapi_schema


def validate_model_identifier(schema: dict, param: str, ref: str) -> None:
    validator = Draft7Validator(schema, resolver=get_ref_resolver(openapi_schema))

    obj = {"id_str": "model_id"}

    try:
        validator.validate(obj)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: 'model_identifier' param {param} failed to validate a "
            f"a 'model identifier' object {obj}"
        )
        raise ValidationError(msg) from None
