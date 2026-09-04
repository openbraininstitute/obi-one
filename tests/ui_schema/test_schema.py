import copy
import logging
from collections import defaultdict
from typing import Any, get_args

import pytest
from jsonschema import ValidationError
from pydantic import TypeAdapter

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.blocks.protocol_and_feature_selection import (  # ruff: ignore[line-too-long]
    SelectEFeaturesByProtocol,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features import (  # ruff: ignore[line-too-long]
    efeatures,
    protocols,
)

from .validate_block import (
    openapi_schema,
    resolve_ref,
    validate_block,
    validate_float_optional,
    validate_hidden_refs_not_required,
    validate_neuron_set_combination,
    validate_select_efeatures_by_protocol,
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
        case UIElement.EMODEL_OPTIMISATION_PARAMETERS:
            validate_emodel_optimisation_parameters(schema, element, ref)
        case _:
            msg = (
                f"Validation error at {config_ref} {element}: 'ui_element' must be 'block_single',"
                f" 'block_dictionary', 'block_union', or 'emodel_optimisation_parameters'."
                f" Got: {ui_element}"
            )
            raise ValueError(msg)


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
        if not root_element_schema.get(SchemaKey.UI_ENABLED, True):
            continue
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
    additional_properties = schema.get("additionalProperties", {})
    if not isinstance(additional_properties, dict):
        msg = (
            f"Validation error at {config_ref}: block_dictionary {key} must have an object "
            "schema in additionalProperties"
        )
        raise TypeError(msg)

    block_schemas = additional_properties.get("oneOf")
    direct_schema = False
    if block_schemas is None:
        block_ref = additional_properties.get("$ref")
        if block_ref is not None:
            block_schemas = [{"$ref": block_ref}]
        elif isinstance(additional_properties.get("properties"), dict):
            block_schemas = [additional_properties]
            direct_schema = True
        else:
            msg = (
                f"Validation error at {config_ref}: block_dictionary {key} must have 'oneOf', "
                "'$ref', or an inline object schema in additionalProperties"
            )
            raise ValueError(msg)

    for block_schema in block_schemas:
        ref = block_schema.get("$ref")

        if ref:
            block_schema = {**block_schema, **resolve_ref(openapi_schema, ref)}  # ruff: ignore[redefined-loop-name]

        validate_scan_config_dependendent_block_components(block_schema, ref, form)

        if direct_schema and not isinstance(block_schema.get("properties"), dict):
            msg = (
                f"Validation error at {config_ref}: block_dictionary {key} must reference an "
                "object schema"
            )
            raise TypeError(msg)
        if not direct_schema:
            validate_block(block_schema, ref)


def validate_block_union(schema: dict, key: str, config_ref: str, form: dict) -> None:
    if schema.get("oneOf") is None:
        msg = f"Validation error at {config_ref}: block_union {key} must have 'oneOf'"
        raise ValueError(msg)

    for block_schema in schema.get("oneOf"):
        ref = block_schema.get("$ref")

        if ref:
            block_schema = {**block_schema, **resolve_ref(openapi_schema, ref)}  # ruff: ignore[redefined-loop-name]

        validate_scan_config_dependendent_block_components(block_schema, ref, form)

        validate_block(block_schema, ref)


def validate_block_single(schema: dict, key: str, ref: str) -> None:
    if not isinstance(schema.get("properties"), dict):
        msg = f"Validation error at {ref}: block_single {key} must have 'properties'"
        raise TypeError(msg)

    validate_block(schema, ref)


def validate_emodel_optimisation_parameters(schema: dict, key: str, ref: str) -> None:
    """Validate the root-level Task 2 mechanisms/optimization-parameter workflow element.

    Structurally this root element is a nested-block object (like ``block_single``),
    but it additionally must carry a ``mechanisms`` property (the
    ``MechanismsBySectionList`` catalogue and section-list filing) so that clients can
    distinguish it from a generic ``block_single`` root field.
    """
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        msg = (
            f"Validation error at {ref}: emodel_optimisation_parameters {key} must have "
            "'properties'"
        )
        raise TypeError(msg)

    if "mechanisms" not in properties:
        msg = (
            f"Validation error at {ref}: emodel_optimisation_parameters {key} must define a "
            "'mechanisms' property (MechanismsBySectionList)."
        )
        raise ValueError(msg)

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
        if not root_element_schema.get(SchemaKey.UI_ENABLED, True):
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


# ---------------------------------------------------------------------------
# Targeted tests for the `select_efeatures_by_protocol` UI element validator.
# ---------------------------------------------------------------------------

# ProtocolAndFeatureSelection.selection uses UIElement.SELECT_EFEATURES_BY_PROTOCOL:
# a $ref to the SelectEFeaturesByProtocol object (type "object") holding the protocols.
SELECT_EFEATURES_BLOCK = "ProtocolAndFeatureSelection"
SELECT_EFEATURES_FIELD = "selection"


def _select_efeatures_schema() -> dict:
    """Return a deep copy of the real `select_efeatures_by_protocol` field schema."""
    return copy.deepcopy(
        openapi_schema["components"]["schemas"][SELECT_EFEATURES_BLOCK]["properties"][
            SELECT_EFEATURES_FIELD
        ]
    )


def test_select_efeatures_by_protocol_valid_schema_passes():
    # The real, generated field references the SelectEFeaturesByProtocol object.
    validate_select_efeatures_by_protocol(
        _select_efeatures_schema(), SELECT_EFEATURES_FIELD, SELECT_EFEATURES_BLOCK
    )


def test_select_efeatures_by_protocol_rejects_missing_object_reference():
    schema = _select_efeatures_schema()
    schema.pop("$ref", None)
    schema.pop("allOf", None)
    with pytest.raises(AssertionError, match="should reference the object"):
        validate_select_efeatures_by_protocol(schema, SELECT_EFEATURES_FIELD, "ref")


def test_efeature_union_schema_exposes_categories_and_doc_anchors():
    assert efeatures.ISICVFeature.efel_doc_anchor == "isi-cv"
    assert (
        efeatures.InvSecondISIFeature.efel_doc_anchor
        == "inv-first-isi-inv-second-isi-inv-third-isi-inv-fourth-isi-inv-fifth-isi-inv-last-isi"
    )

    schema = TypeAdapter(efeatures.EFeatureUnion).json_schema()
    definitions = schema["$defs"]

    assert len(definitions) == 146
    assert len(schema["oneOf"]) == len(definitions)
    assert {
        definition["extra"][SchemaKey.EFEL_FEATURE_CATEGORY] for definition in definitions.values()
    } == {"spike_event", "spike_shape", "subthreshold"}
    assert all(
        SchemaKey.EFEL_DOC_ANCHOR in definition["extra"] for definition in definitions.values()
    )
    assert definitions["ISICVFeature"]["extra"][SchemaKey.EFEL_DOC_ANCHOR] == "isi-cv"
    assert (
        definitions["InvSecondISIFeature"]["extra"][SchemaKey.EFEL_DOC_ANCHOR]
        == "inv-first-isi-inv-second-isi-inv-third-isi-inv-fourth-isi-inv-fifth-isi-inv-last-isi"
    )


def test_efeature_base_schema_omits_empty_category_and_anchor():
    """The base EFeature has empty category/anchor; the False branches must be covered."""
    schema = TypeAdapter(efeatures.EFeature).json_schema()
    extra = schema.get("extra", {})
    assert SchemaKey.EFEL_FEATURE_CATEGORY not in extra
    assert SchemaKey.EFEL_DOC_ANCHOR not in extra


def test_efel_settings_overrides_all_branches():
    """Cover every branch of EFeature.efel_settings_overrides()."""

    # 1. Defaults only — all conditionals False (no threshold, no resampling,
    #    stim_start/stim_end are 0.0 so skipped).
    feature = efeatures.ISICVFeature()
    assert feature.efel_settings_overrides() == {}

    # 2. spike_detection_threshold set — Threshold branch True.
    feature = efeatures.ISICVFeature(spike_detection_threshold=-20.0)
    assert feature.efel_settings_overrides() == {"Threshold": -20.0}

    # 3. trace_resampling_timestep set — interp_step branch True.
    feature = efeatures.ISICVFeature(trace_resampling_timestep=0.1)
    assert feature.efel_settings_overrides() == {"interp_step": 0.1}

    # 4. stim_start and stim_end non-zero — stim branch True.
    feature = efeatures.ISICVFeature(stim_start=100.0, stim_end=900.0)
    assert feature.efel_settings_overrides() == {"stim_start": 100.0, "stim_end": 900.0}

    # 5. Everything set — all branches True simultaneously.
    feature = efeatures.ISICVFeature(
        spike_detection_threshold=-20.0,
        trace_resampling_timestep=0.1,
        stim_start=100.0,
        stim_end=900.0,
    )
    assert feature.efel_settings_overrides() == {
        "Threshold": -20.0,
        "interp_step": 0.1,
        "stim_start": 100.0,
        "stim_end": 900.0,
    }


def test_protocols_narrow_features_and_catalogue_is_declared_once():
    """The universal union belongs to ``extra_features_by_protocol`` and nowhere else.

    Each occurrence is copied when the UI dereferences the schema, and 26 copies of a
    146-branch union exceed what the browser can compile into one validator.
    """
    universal_size = len(TypeAdapter(efeatures.EFeatureUnion).json_schema()["oneOf"])
    schema = SelectEFeaturesByProtocol.model_json_schema()

    catalogue = schema["properties"]["extra_features_by_protocol"]["additionalProperties"]["items"]
    assert len(catalogue["oneOf"]) == universal_size

    for protocol_class in get_args(get_args(protocols.ProtocolUnion)[0]):
        feature_schema = protocol_class.model_json_schema()["properties"]["features"]["items"]
        assert 0 < len(feature_schema["oneOf"]) < universal_size


def test_features_for_merges_extras_without_duplicating_defaults():
    selection = SelectEFeaturesByProtocol()
    protocol = selection.protocols[0]
    already_selected = type(protocol.features[0])

    extended = SelectEFeaturesByProtocol(
        extra_features_by_protocol={
            type(protocol).__name__: (efeatures.SagAmplitudeFeature(), already_selected()),
        },
    )
    merged = extended.features_for(extended.protocols[0])
    names = [type(feature).__name__ for feature in merged]

    assert names.count(already_selected.__name__) == 1
    assert "SagAmplitudeFeature" in names
    assert len(merged) == len(protocol.features) + 1


def test_features_for_ignores_extras_keyed_to_another_protocol():
    selection = SelectEFeaturesByProtocol(
        extra_features_by_protocol={"NotAProtocolInThisSelection": (efeatures.ISICVFeature(),)},
    )
    for protocol in selection.protocols:
        assert selection.features_for(protocol) == protocol.features
