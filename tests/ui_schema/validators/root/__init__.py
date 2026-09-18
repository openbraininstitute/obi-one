"""Locked root (config-level) validators.

Root UI elements render an entire block and drive main-panel behaviour, so a weakened root
validator has a larger blast radius than a block-element one. Each root `ui_element` has a
validator module here; `validate_config` is the top-level form walker and `validate_root_element`
(in `config.py`) dispatches through `ROOT_VALIDATOR_BY_UI_ELEMENT`, which lives in the shared
`tests/ui_schema/validators/registry.py` alongside the block-element registry.

**This subpackage is locked.** Configs must be fixed to match the spec these validators
enforce; the validators must not be weakened. CI rejects any PR that modifies or deletes the
locked files here unless it carries the `change-validators` label. This `__init__.py` is
guard-exempt, as is `registry.py` in the parent package, so new root elements can be registered.

To add a new root UI element:

1. Add the member to `obi_one.core.schema.UIElement`.
2. Create `<element>.py` here with a validator using the signature
   `(schema, element, ref, config_ref, form)`.
3. Register it in `ROOT_VALIDATOR_BY_UI_ELEMENT` in `tests/ui_schema/validators/registry.py`.
4. Adding the file touches this locked subpackage, so apply the `change-validators` label so a
   reviewer signs off (registering it in `registry.py` is guard-exempt).
"""

from .block_dictionary import validate_block_dictionary
from .block_single import validate_block_single
from .block_union import validate_root_block_union
from .config import validate_config, validate_root_element
from .shared import (
    validate_array,
    validate_block_usability_dictionary,
    validate_dict,
    validate_group_order,
    validate_scan_config_dependendent_block_components,
)

__all__ = [
    "validate_array",
    "validate_block_dictionary",
    "validate_block_single",
    "validate_block_usability_dictionary",
    "validate_config",
    "validate_dict",
    "validate_group_order",
    "validate_root_block_union",
    "validate_root_element",
    "validate_scan_config_dependendent_block_components",
]
