"""Validator for the `block_dictionary` root UI element."""

from .shared import (
    openapi_schema,
    resolve_ref,
    validate_scan_config_dependendent_block_components,
)
from tests.ui_schema.validate_block import validate_block


def validate_block_dictionary(
    schema: dict,
    key: str,
    ref: str,  # ruff: ignore[unused-function-argument]
    config_ref: str,
    form: dict,
) -> None:
    # Uniform root-validator signature (schema, element, ref, config_ref, form); the per-block
    # `$ref` is resolved from each member below, so the element-level `ref` is unused here.
    additional_properties = schema.get("additionalProperties", {})
    block_schemas = additional_properties.get("oneOf")
    if block_schemas is None:
        block_ref = additional_properties.get("$ref")
        if block_ref is None:
            msg = (
                f"Validation error at {config_ref}: block_dictionary {key} must have 'oneOf'"
                " or '$ref' in additionalProperties"
            )
            raise ValueError(msg)
        block_schemas = [{"$ref": block_ref}]

    for block_schema in block_schemas:
        block_schema_ref = block_schema.get("$ref")

        if block_schema_ref:
            block_schema = {  # ruff: ignore[redefined-loop-name]
                **block_schema,
                **resolve_ref(openapi_schema, block_schema_ref),
            }

        validate_scan_config_dependendent_block_components(block_schema, block_schema_ref, form)

        validate_block(block_schema, block_schema_ref)
