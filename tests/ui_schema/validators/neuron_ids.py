"""Validator for the `neuron_ids` block UI element."""

from jsonschema import Draft7Validator, ValidationError

from .shared import openapi_resolver


def validate_neuron_ids(schema: dict, param: str, ref: str) -> None:
    validator = Draft7Validator(schema, resolver=openapi_resolver)

    neuron_ids = {"elements": [1]}
    try:
        validator.validate(neuron_ids)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: 'neuron_ids' param {param} failed to validate a "
            f"neuron_ids object {neuron_ids}"
        )
        raise ValidationError(msg) from None
