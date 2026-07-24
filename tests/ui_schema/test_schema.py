import copy
import logging
from collections import defaultdict
from typing import Any

import pytest
from jsonschema import ValidationError

from obi_one.core.schema import SchemaKey, UIElement

from .validate_block import (
    openapi_schema,
    resolve_ref,
    validate_block,
    validate_float_optional,
    validate_hidden_refs_not_required,
    validate_neuron_set_combination,
    validate_string,
    validate_type,
)

L = logging.getLogger()


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


def validate_root_element(
    schema: dict, element: str, ref: str, config_ref: str, form: dict
) -> None:
    match ui_element := schema.get(SchemaKey.UI_ELEMENT):
        case UIElement.BLOCK_SINGLE:
            validate_block_single(schema, element, ref)
        case UIElement.BLOCK_DICTIONARY:
            validate_block_dictionary(schema, element, config_ref, form)
        case UIElement.BLOCK_UNION:
            validate_block_union(schema, element, config_ref, form)
        case _:
            msg = (
                f"Validation error at {config_ref} {element}: 'ui_element' must be 'block_single',"
                f" 'block_dictionary', or 'block_union'. Got: {ui_element}"
            )
            raise ValueError(msg)


def validate_dict(schema: dict, element: str, form_ref: str) -> None:
    if type(schema.get(element, {})) is not dict:
        msg = f"Validation error at {form_ref}: {element} must be a dictionary"
        raise ValueError(msg)


def validate_group_order(schema: dict, form_ref: str) -> None:  # noqa: C901
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


def validate_scan_config_dependendent_block_components(block_schema, ref, form):
    validate_block_usability_dictionary(block_schema, ref, form)


def validate_block_dictionary(schema: dict, key: str, config_ref: str, form: dict) -> None:
    if schema.get("additionalProperties", {}).get("oneOf") is None:
        msg = (
            f"Validation error at {config_ref}: block_dictionary {key} must have 'oneOf'"
            "in additionalProperties"
        )
        raise ValueError(msg)

    for block_schema in schema.get("additionalProperties", {}).get("oneOf"):
        ref = block_schema.get("$ref")

        if ref:
            block_schema = {**block_schema, **resolve_ref(openapi_schema, ref)}  # noqa: PLW2901

        validate_scan_config_dependendent_block_components(block_schema, ref, form)

        validate_block(block_schema, ref)


def validate_block_union(schema: dict, key: str, config_ref: str, form: dict) -> None:
    if schema.get("oneOf") is None:
        msg = f"Validation error at {config_ref}: block_union {key} must have 'oneOf'"
        raise ValueError(msg)

    for block_schema in schema.get("oneOf"):
        ref = block_schema.get("$ref")

        if ref:
            block_schema = {**block_schema, **resolve_ref(openapi_schema, ref)}  # noqa: PLW2901

        validate_scan_config_dependendent_block_components(block_schema, ref, form)

        validate_block(block_schema, ref)


def validate_block_single(schema: dict, key: str, ref: str) -> None:
    if not isinstance(schema.get("properties"), dict):
        msg = f"Validation error at {ref}: block_single {key} must have 'properties'"
        raise TypeError(msg)

    validate_block(schema, ref)


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
            root_element_schema = {  # noqa: PLW2901
                **root_element_schema,
                **resolve_ref(openapi_schema, ref),
            }

        validate_string(root_element_schema, "title", f"{root_element} at {config_ref}")
        validate_string(root_element_schema, "description", f"{root_element} at {config_ref}")

        validate_root_element(root_element_schema, root_element, ref, config_ref, form)


def test_schema() -> None:
    for path, value in openapi_schema["paths"].items():
        if not path.startswith("/generated"):
            continue

        schema_ref = value["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]

        schema = resolve_ref(openapi_schema, schema_ref)
        validate_config(schema, schema_ref)


# ---------------------------------------------------------------------------
# Targeted tests for the `neuron_set_combination` UI element validator.
# ---------------------------------------------------------------------------

# Concrete blocks whose `combined_with` field uses UIElement.NEURON_SET_COMBINATION.
# BiophysicalCombinedNeuronSet exercises the multi-reference (anyOf) neuron set slot, while
# PointCombinedNeuronSet exercises the single-reference ($ref) slot.
COMBINATION_BLOCKS = ["BiophysicalCombinedNeuronSet", "PointCombinedNeuronSet"]


def _combination_schema(block_name: str) -> dict:
    """Return a deep copy of a real `combined_with` (neuron_set_combination) field schema."""
    return copy.deepcopy(
        openapi_schema["components"]["schemas"][block_name]["properties"]["combined_with"]
    )


@pytest.mark.parametrize("block_name", COMBINATION_BLOCKS)
def test_neuron_set_combination_valid_schema_passes(block_name):
    # The real, generated schema must validate for both the single-$ref and anyOf neuron set slots.
    validate_neuron_set_combination(_combination_schema(block_name), "combined_with", block_name)


def test_neuron_set_combination_rejects_non_array():
    schema = _combination_schema("BiophysicalCombinedNeuronSet")
    schema["type"] = "object"
    with pytest.raises(ValidationError, match="should be of type 'array'"):
        validate_neuron_set_combination(schema, "combined_with", "ref")


def test_neuron_set_combination_rejects_wrong_tuple_arity():
    schema = _combination_schema("BiophysicalCombinedNeuronSet")
    schema["items"]["maxItems"] = 3
    with pytest.raises(ValidationError, match="2-tuples"):
        validate_neuron_set_combination(schema, "combined_with", "ref")


def test_neuron_set_combination_rejects_reference_types_mismatch():
    schema = _combination_schema("BiophysicalCombinedNeuronSet")
    schema["reference_types"] = [*schema["reference_types"], "NonExistentReference"]
    with pytest.raises(ValidationError, match="match 'reference_types'"):
        validate_neuron_set_combination(schema, "combined_with", "ref")


def test_neuron_set_combination_rejects_bad_operation_enum():
    schema = _combination_schema("BiophysicalCombinedNeuronSet")
    # Drop an operation so the enum no longer matches the SetOperation members.
    schema["items"]["prefixItems"][1]["enum"] = ["union", "intersect"]
    with pytest.raises(ValidationError, match="set operations"):
        validate_neuron_set_combination(schema, "combined_with", "ref")


def test_neuron_set_combination_rejects_non_list_reference_types():
    schema = _combination_schema("BiophysicalCombinedNeuronSet")
    schema["reference_types"] = "BiophysicalNeuronSetReference"
    with pytest.raises(ValueError, match="must be a list of strings"):
        validate_neuron_set_combination(schema, "combined_with", "ref")


# ---------------------------------------------------------------------------
# Targeted tests for the `float_optional` UI element validator.
# ---------------------------------------------------------------------------

# IDRestProtocol.spike_detection_threshold uses UIElement.FLOAT_OPTIONAL (a nullable
# `float | None` eFEL override where `null` means "inherit from the level above").
FLOAT_OPTIONAL_BLOCK = "IDRestProtocol"
FLOAT_OPTIONAL_FIELD = "spike_detection_threshold"


def _float_optional_schema() -> dict:
    """Return a deep copy of a real `float_optional` field schema."""
    return copy.deepcopy(
        openapi_schema["components"]["schemas"][FLOAT_OPTIONAL_BLOCK]["properties"][
            FLOAT_OPTIONAL_FIELD
        ]
    )


def test_float_optional_valid_schema_passes():
    # The real, generated schema (a `number | null` union) must validate.
    validate_float_optional(_float_optional_schema(), FLOAT_OPTIONAL_FIELD, FLOAT_OPTIONAL_BLOCK)


def test_float_optional_rejects_non_number_first():
    schema = _float_optional_schema()
    schema["anyOf"][0] = {"type": "string"}
    with pytest.raises(ValidationError, match="number"):
        validate_float_optional(schema, FLOAT_OPTIONAL_FIELD, "ref")


def test_float_optional_rejects_missing_null():
    schema = _float_optional_schema()
    schema["anyOf"][1] = {"type": "array", "items": {"type": "number"}}
    with pytest.raises(ValidationError, match="null"):
        validate_float_optional(schema, FLOAT_OPTIONAL_FIELD, "ref")
