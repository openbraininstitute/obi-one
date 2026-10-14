"""Validator for the `distance_function_input_nullable` block UI element."""

from jsonschema import ValidationError

from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import (
    MAX_DISTANCE_FUNCTION_LENGTH,
)


def validate_distance_function_input_nullable(schema: dict, param: str, ref: str) -> None:
    # Nullable distance function (`str | None`): an anyOf whose first branch is the string
    # carrying max_length and whose second branch is null. The string must come first so the
    # frontend reads `maxLength` from a fixed position without branching.
    any_of = schema.get("anyOf")
    if not isinstance(any_of, list) or len(any_of) != 2:
        msg = (
            f"Validation error at {ref}: distance_function_input_nullable param {param} must be an "
            f"'anyOf' of a string and null. Got: {schema}"
        )
        raise ValidationError(msg) from None
    string_branch, null_branch = any_of
    if string_branch.get("type") != "string":
        msg = (
            f"Validation error at {ref}: distance_function_input_nullable param {param} must have "
            f"the string as its first anyOf branch. Got: {string_branch}"
        )
        raise ValidationError(msg) from None
    if null_branch.get("type") != "null":
        msg = (
            f"Validation error at {ref}: distance_function_input_nullable param {param} must have "
            f"null as its second anyOf branch. Got: {null_branch}"
        )
        raise ValidationError(msg) from None
    max_length = string_branch.get("maxLength")
    if max_length != MAX_DISTANCE_FUNCTION_LENGTH:
        msg = (
            f"Validation error at {ref}: distance_function_input_nullable param {param} must "
            f"declare max_length=MAX_DISTANCE_FUNCTION_LENGTH ({MAX_DISTANCE_FUNCTION_LENGTH}) on "
            f"its string branch. Got: {max_length}"
        )
        raise ValidationError(msg) from None
