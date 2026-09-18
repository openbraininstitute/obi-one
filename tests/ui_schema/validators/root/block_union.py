"""Validator for the `block_union` root UI element.

Named `validate_root_block_union` to distinguish it from the block-element `block_union`
validator (`tests.ui_schema.validators.block_union`), which validates a field within a block
rather than a root element rendering a whole block.
"""

from .shared import (
    openapi_schema,
    resolve_ref,
    validate_scan_config_dependendent_block_components,
)
from tests.ui_schema.validate_block import validate_block


def validate_root_block_union(
    schema: dict,
    key: str,
    ref: str,  # ruff: ignore[unused-function-argument]
    config_ref: str,
    form: dict,
) -> None:
    # Uniform root-validator signature (schema, element, ref, config_ref, form); the per-block
    # `$ref` is resolved from each union member below, so the element-level `ref` is unused here.
    if schema.get("oneOf") is None:
        msg = f"Validation error at {config_ref}: block_union {key} must have 'oneOf'"
        raise ValueError(msg)

    for block_schema in schema.get("oneOf"):
        block_schema_ref = block_schema.get("$ref")

        if block_schema_ref:
            block_schema = {  # ruff: ignore[redefined-loop-name]
                **block_schema,
                **resolve_ref(openapi_schema, block_schema_ref),
            }

        validate_scan_config_dependendent_block_components(block_schema, block_schema_ref, form)

        validate_block(block_schema, block_schema_ref)
