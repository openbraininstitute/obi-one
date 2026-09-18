"""Top-level config (form) validator and root-element dispatch.

`validate_config` walks a generated form schema: it checks the form-level fields
(title/description/default labels/group order/hidden refs) and dispatches every root element
to its validator via `validate_root_element`, which looks the validator up in
`ROOT_VALIDATOR_BY_UI_ELEMENT` (in `tests/ui_schema/validators/registry.py`).

**This module is locked.** It enforces form-level structure that governs how a whole config
renders; weakening it has a large blast radius. Fix the config to match the spec; changing the
spec requires the `change-validators` label.
"""

import logging

from obi_one.core.schema import SchemaKey

from .shared import (
    openapi_schema,
    resolve_ref,
    validate_dict,
    validate_group_order,
)
from tests.ui_schema.validate_block import (
    validate_hidden_refs_not_required,
    validate_type,
)
from tests.ui_schema.validators.shared import validate_string

L = logging.getLogger()


def validate_root_element(
    schema: dict, element: str, ref: str, config_ref: str, form: dict
) -> None:
    """Dispatch a root element to the validator registered for its UI element.

    An unregistered `ui_element` is a hard error so new root elements cannot be added without a
    validator.
    """
    # Imported lazily to break an import cycle: the registry imports the root validators, which
    # import `validate_block`, which this subpackage depends on transitively.
    from tests.ui_schema.validators.registry import (  # ruff: ignore[import-outside-top-level]
        ROOT_VALIDATOR_BY_UI_ELEMENT,
    )

    ui_element = schema.get(SchemaKey.UI_ELEMENT)
    validator = ROOT_VALIDATOR_BY_UI_ELEMENT.get(ui_element)
    if validator is None:
        msg = (
            f"Validation error at {config_ref} {element}: 'ui_element' must be 'block_single',"
            f" 'block_dictionary', or 'block_union'. Got: {ui_element}"
        )
        raise ValueError(msg)

    validator(schema, element, ref, config_ref, form)


def validate_config(form: dict, config_ref: str) -> None:
    if not form.get(SchemaKey.UI_ENABLED):
        L.info(f"Form {config_ref} is disabled, skipping validation.")
        return

    L.info(f"Validating form {config_ref} ...")

    validate_string(form, "title", config_ref)
    validate_string(form, "description", config_ref)
    validate_dict(form, SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS, config_ref)
    validate_group_order(form, config_ref)
    validate_hidden_refs_not_required(form, config_ref)

    for root_element, root_element_schema in form.get("properties", {}).items():
        if root_element == "type":
            validate_type(root_element_schema, config_ref)
            continue

        ref = root_element_schema.get("$ref")

        if ref:
            root_element_schema = {  # ruff: ignore[redefined-loop-name]
                **root_element_schema,
                **resolve_ref(openapi_schema, ref),
            }

        validate_string(root_element_schema, "title", f"{root_element} at {config_ref}")
        validate_string(root_element_schema, "description", f"{root_element} at {config_ref}")

        validate_root_element(root_element_schema, root_element, ref, config_ref, form)
