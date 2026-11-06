"""Locked root (config-level) validators (one module per root `ui_element`).

`validate_config` (in `config.py`) is the top-level form walker; `validate_root_element` there
dispatches through `ROOT_VALIDATOR_BY_UI_ELEMENT` in `tests/ui_schema/validators/registry.py`,
which is the single place to register a root validator. Import a validator from its own module;
this package re-exports nothing. See the "Enabling ScanConfigs in the UI" section of AGENTS.md
and `docs/gui-definition-spec/gui-definition.md` for the lock policy and how to add an element.
"""
