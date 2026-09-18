"""Shared helpers for root (config-level) validators.

These are the config-level structural checks reused across the root-element validators:
array/dict typing, the `group_order` layout rules, and the block-usability dictionary check.

**This module is locked.** Root elements render an entire block and drive main-panel
behaviour, so weakening one of these checks has a large blast radius. Fix the config to match
the spec rather than loosening the check; changing the spec requires the `change-validators`
label (see `.github/workflows/run-tests.yml`).
"""

from collections import defaultdict
from typing import Any

from obi_one.core.schema import SchemaKey

from tests.ui_schema.validators.shared import openapi_schema, resolve_ref

__all__ = [
    "openapi_schema",
    "resolve_ref",
    "validate_array",
    "validate_block_usability_dictionary",
    "validate_dict",
    "validate_group_order",
    "validate_scan_config_dependendent_block_components",
]


def validate_array(schema: dict, prop: str, array_type: type, ref: str) -> list[Any]:
    value = schema.get(prop, [])
    for item in value:
        if type(item) is not array_type:
            msg = (
                f"Validation error at {ref}: Array items must be of type {array_type}."
                f"Got: {type(item)}"
            )
            raise ValueError(msg)

    return value


def validate_dict(schema: dict, element: str, form_ref: str) -> None:
    if type(schema.get(element, {})) is not dict:
        msg = f"Validation error at {form_ref}: {element} must be a dictionary"
        raise ValueError(msg)


def validate_group_order(schema: dict, form_ref: str) -> None:  # ruff: ignore[complex-structure]
    groups: list[str] = validate_array(schema, SchemaKey.GROUP_ORDER, str, form_ref)

    used_groups: dict[str, list[int]] = defaultdict(list)

    for root_element, root_element_schema in schema.get("properties", {}).items():
        if root_element == "type":
            continue

        group = root_element_schema.get(SchemaKey.GROUP)
        group_order = root_element_schema.get(SchemaKey.GROUP_ORDER)
        if not group:
            msg = f"Validation error at {form_ref}: {root_element} must have a group"
            raise ValueError(msg)

        if group_order is None:
            msg = f"Validation error at {form_ref}: {root_element} must have a group_order"
            raise ValueError(msg)

        if not isinstance(group_order, int):
            msg = f"Validation error at {form_ref}: {root_element} group_order must be an integer"
            raise TypeError(msg)

        if not isinstance(group, str):
            msg = f"Validation error at {form_ref}: {root_element} group must be a string"
            raise TypeError(msg)

        if group not in groups:
            msg = (
                f"Validation error at {form_ref}: {root_element} has group '{group}'"
                "not in root group_order"
            )
            raise ValueError(msg)

        used_groups[group].append(group_order)

    if extra_groups := (set(groups) - set(used_groups.keys())):
        msg = (
            f"Validation error at {form_ref}: group_order contains groups not used in properties"
            f" {extra_groups}"
        )

        raise ValueError(msg)

    for used_group, used_group_orders in used_groups.items():
        if len(used_group_orders) != len(set(used_group_orders)):
            msg = (
                f"Validation error at {form_ref}: group '{used_group}' has duplicate group_order"
                f" values: {used_group_orders}"
            )
            raise ValueError(msg)


def validate_block_usability_dictionary(block_schema: dict, ref: str, form: dict) -> None:
    block_usability_dictionary = block_schema.get(SchemaKey.BLOCK_USABILITY_DICTIONARY)
    if block_usability_dictionary is not None:
        if type(block_usability_dictionary) is not dict:
            msg = (
                f"Validation error at {ref}: 'block_usability_dictionary' must be a dictionary "
                f"if defined."
            )
            raise ValueError(msg)

        property_group = block_usability_dictionary.get(SchemaKey.PROPERTY_GROUP)
        property_value = block_usability_dictionary.get(SchemaKey.PROPERTY)
        false_message = block_usability_dictionary.get(SchemaKey.FALSE_MESSAGE)

        if property_group is None or property_value is None or false_message is None:
            msg = (
                f"Validation error at {ref}: 'block_usability_dictionary' must have "
                f"'property_group', 'property', and 'false_message' keys when defined "
                f"in the block schema."
            )
            raise ValueError(msg)

        if (
            type(property_group) is not str
            or type(property_value) is not str
            or type(false_message) is not str
        ):
            msg = (
                f"Validation error at {ref}: 'property_group', 'property', and 'false_message' "
                f"must be strings in 'block_usability_dictionary' when defined in the block "
                f"schema."
            )
            raise TypeError(msg)

        schema_property_endpoints = form.get(SchemaKey.PROPERTY_ENDPOINTS)
        if (
            schema_property_endpoints is None
            or type(schema_property_endpoints) is not dict
            or schema_property_endpoints.get(property_group) is None
            or type(schema_property_endpoints.get(property_group)) is not str
            or len(schema_property_endpoints.get(property_group)) == 0
        ):
            msg = (
                f"Validation error at {ref}: 'property_endpoints' must be defined in the root "
                f"schema and must be a dictionary with a non-empty string value for the key "
                f"specified in 'property_group' when 'block_usability_entity_dependent' is defined"
            )
            raise ValueError(msg)


def validate_scan_config_dependendent_block_components(
    block_schema: dict, ref: str, form: dict
) -> None:
    validate_block_usability_dictionary(block_schema, ref, form)
