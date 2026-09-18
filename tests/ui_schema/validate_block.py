"""Block validation entry point.

`validate_block` walks a block schema and dispatches every non-hidden field to its
per-element validator. Those per-element validators live in the locked
`tests.ui_schema.validators` package (one module per `UIElement`) and are looked up through
`VALIDATOR_BY_UI_ELEMENT`. This module keeps only the block-level orchestration
(`validate_block`, `validate_block_elements`) plus the two block-level structural checks
(`validate_hidden_refs_not_required`, `validate_type`).

Individual validators are intentionally NOT defined here: they are locked so that configs
get fixed to match the spec rather than the spec being weakened to admit a bad config. See
`tests/ui_schema/validators/__init__.py` for how to add a new UI element.

`validators.block_union` imports `validate_block` from here lazily (function-local) to
avoid a circular import, so this module can import the validators package at the top level.
"""

import logging

from obi_one.core.schema import SchemaKey

from tests.ui_schema.validators import VALIDATOR_BY_UI_ELEMENT
from tests.ui_schema.validators.shared import validate_string

L = logging.getLogger()


def validate_hidden_refs_not_required(schema: dict, ref: str) -> None:
    for key, param_schema in schema["properties"].items():
        if param_schema.get(SchemaKey.UI_HIDDEN) and key in schema.get("required", []):
            msg = (
                f"The hidden reference {key} is marked as required in the schema"
                f" but shouldn't be\n\n In {ref}"
            )
            raise ValueError(msg)


def validate_type(schema: dict, ref: str) -> None:
    if not isinstance(schema, dict):
        msg = f"Validation error at {ref}: 'type' schema must be a dictionary"
        raise TypeError(msg)

    if not schema.get("default"):
        msg = f"Validation error at {ref}: 'type' must have a default"
        raise ValueError(msg)


def validate_block_elements(param: str, schema: dict, ref: str) -> None:
    """Dispatch a block field to the validator registered for its UI element.

    The mapping lives in `tests.ui_schema.validators.VALIDATOR_BY_UI_ELEMENT`; an
    unregistered `ui_element` is a hard error so new elements cannot be added without a
    validator.
    """
    ui_element = schema.get(SchemaKey.UI_ELEMENT)
    validator = VALIDATOR_BY_UI_ELEMENT.get(ui_element)
    if validator is None:
        msg = f"Validation error at {ref}, param {param}: {ui_element} is not a valid ui_element"
        raise ValueError(msg)

    validator(schema, param, ref)


def validate_block(schema: dict, ref: str) -> None:
    validate_hidden_refs_not_required(schema, ref)

    validate_string(schema, "title", ref)
    validate_string(schema, "description", ref)

    for param, param_schema in schema.get("properties", {}).items():
        if param_schema.get(SchemaKey.UI_HIDDEN):
            continue

        if param == "type":
            validate_type(param_schema, ref)
            continue

        validate_string(param_schema, "title", f"{param} at {ref}")
        validate_string(param_schema, "description", f"{param} at {ref}")
        validate_block_elements(param, param_schema, ref)
