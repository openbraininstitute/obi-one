"""Validator for the `block_single` root UI element."""

from tests.ui_schema.validate_block import validate_block


def validate_block_single(
    schema: dict,
    key: str,
    ref: str,
    config_ref: str,  # ruff: ignore[unused-function-argument]
    form: dict,  # ruff: ignore[unused-function-argument]
) -> None:
    # Uniform root-validator signature (schema, element, ref, config_ref, form); a single block
    # validates in place, so the config_ref/form context is unused here.
    if not isinstance(schema.get("properties"), dict):
        msg = f"Validation error at {ref}: block_single {key} must have 'properties'"
        raise TypeError(msg)

    validate_block(schema, ref)
