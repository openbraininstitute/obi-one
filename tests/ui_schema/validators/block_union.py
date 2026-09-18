"""Validator for the `block_union` block UI element."""

from .shared import openapi_schema, resolve_ref


def validate_block_union(schema: dict, param: str, ref: str) -> None:
    # Imported lazily (function-local) to break a circular import: `validate_block` lives in
    # `validate_block.py`, whose package (`validators`) imports this module.
    from tests.ui_schema.validate_block import (  # ruff: ignore[import-outside-top-level]
        validate_block,
    )

    if schema.get("oneOf") is None:
        msg = f"Validation error at {ref}: block_union param {param} must have 'oneOf'"
        raise ValueError(msg)

    for block_schema in schema.get("oneOf"):
        block_ref = block_schema.get("$ref")
        resolved_block_schema = block_schema

        if block_ref:
            resolved_block_schema = {
                **block_schema,
                **resolve_ref(openapi_schema, block_ref),
            }

        validate_block(resolved_block_schema, block_ref)
