"""Locked, per-element validators for block UI elements (one module per `ui_element`).

Import a validator from its own module; this package re-exports nothing. `registry.py` maps
each `UIElement` to its validator and is the single place to register one. See the "Enabling
ScanConfigs in the UI" section of AGENTS.md and `docs/gui-definition-spec/gui-definition.md`
for the lock policy and how to add an element.
"""
