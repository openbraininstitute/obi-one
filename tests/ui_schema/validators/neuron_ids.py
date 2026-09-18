"""Validator for the `neuron_ids` block UI element."""

from jsonschema import Draft7Validator, RefResolver, ValidationError

from .shared import openapi_schema


def validate_neuron_ids(schema: dict, param: str, ref: str) -> None:
    resolver = RefResolver.from_schema(openapi_schema)
    validator = Draft7Validator(schema, resolver=resolver)

    neuron_ids = {"elements": [1]}
    try:
        validator.validate(neuron_ids)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: 'neuron_ids' param {param} failed to validate a "
            f"neuron_ids object {neuron_ids}"
        )
        raise ValidationError(msg) from None
