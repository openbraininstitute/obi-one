"""Validator for the `float_parameter_sweep` block UI element."""

from jsonschema import ValidationError, validate

from obi_one.core.schema import UIElement

from .shared import (
    determine_minimum_valid_numeric_value,
    validate_numeric_single_and_list_types,
)


def validate_float_param_sweep(schema: dict, param: str, ref: str) -> None:
    validate_numeric_single_and_list_types(
        schema, param, ref, "number", UIElement.FLOAT_PARAMETER_SWEEP
    )
    test_value = determine_minimum_valid_numeric_value(schema)

    try:
        validate(test_value, schema)

    except ValidationError:
        msg = (
            f"Validation error at {ref}: float_parameter_sweep param {param} failed "
            "to validate a float"
        )
        raise ValidationError(msg) from None

    try:
        validate([test_value], schema)

    except ValidationError:
        msg = (
            f"Validation error at {ref}: float_parameter_sweep param {param} failed "
            "to validate a float array"
        )
        raise ValidationError(msg) from None
