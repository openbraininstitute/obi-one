"""Validator for the `neuron_ids` block UI element."""

from jsonschema import Draft7Validator, ValidationError

from .shared import get_ref_resolver, openapi_schema


def validate_neuron_ids(schema: dict, param: str, ref: str) -> None:
    validator = Draft7Validator(schema, resolver=get_ref_resolver(openapi_schema))

    neuron_ids = {"elements": [1]}
    try:
        validator.validate(neuron_ids)
    except ValidationError:
        msg = (
            f"Validation error at {ref}: 'neuron_ids' param {param} failed to validate a "
            f"neuron_ids object {neuron_ids}"
        )
        raise ValidationError(msg) from None
