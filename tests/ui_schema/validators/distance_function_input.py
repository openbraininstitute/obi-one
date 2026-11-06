"""Validator for the `distance_function_input` block UI element."""

from jsonschema import ValidationError

from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import (
    MAX_DISTANCE_FUNCTION_LENGTH,
)

from .shared import validate_string_param


def validate_distance_function_input(schema: dict, param: str, ref: str) -> None:
    # Non-nullable distance function: a plain string carrying max_length at the schema root
    # (so the frontend reads `maxLength` directly, with no structural branching). Nullable
    # fields must use `distance_function_input_nullable` instead.
    validate_string_param(schema, param, ref)

    if schema.get("type") != "string":
        msg = (
            f"Validation error at {ref}: distance_function_input param {param} must be a plain "
            f"'string' (use distance_function_input_nullable for `str | None`). Got: {schema}"
        )
        raise ValidationError(msg) from None
    max_length = schema.get("maxLength")
    if max_length != MAX_DISTANCE_FUNCTION_LENGTH:
        msg = (
            f"Validation error at {ref}: distance_function_input param {param} must declare "
            f"max_length=MAX_DISTANCE_FUNCTION_LENGTH ({MAX_DISTANCE_FUNCTION_LENGTH}) at the "
            f"schema root. Got: {max_length}"
        )
        raise ValidationError(msg) from None
