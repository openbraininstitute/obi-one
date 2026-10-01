import copy
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
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import (
    MAX_DISTANCE_FUNCTION_LENGTH,
)

from .validators import (
    openapi_schema,
    resolve_ref,
    validate_distance_function_input,
    validate_distance_function_input_nullable,
    validate_float_optional,
    validate_neuron_set_combination,
    validate_select_efeatures_by_protocol,
)
from .validators.root import (
    SECTION_LIST_CHOICE_KEYS,
    validate_config,
    validate_emodel_optimisation_parameters,
    validate_section_list_choices,
    validate_section_list_property_names,
)


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


# ---------------------------------------------------------------------------
# Targeted tests for the `emodel_optimisation_parameters` section-list `choices`.
# ---------------------------------------------------------------------------

# MechanismsBySectionList.mechanism_regions exposes the section-list `choices` list that
# drives the custom Task 2 frontend (availability, label, and ordering metadata).
SECTION_LIST_CHOICES_BLOCK = "MechanismsBySectionList"
SECTION_LIST_CHOICES_FIELD = "mechanism_regions"


def _mechanism_regions_schema() -> dict:
    """Return a deep copy of the real `mechanism_regions` field schema."""
    return copy.deepcopy(
        openapi_schema["components"]["schemas"][SECTION_LIST_CHOICES_BLOCK]["properties"][
            SECTION_LIST_CHOICES_FIELD
        ]
    )


def test_section_list_choices_valid_schema_passes():
    # The real, generated schema must expose a well-formed `choices` list.
    validate_section_list_choices(
        _mechanism_regions_schema(), SECTION_LIST_CHOICES_FIELD, SECTION_LIST_CHOICES_BLOCK
    )


def test_section_list_choices_expose_expected_element_structure():
    schema = _mechanism_regions_schema()
    choices = schema["choices"]

    assert isinstance(choices, list)
    assert choices

    # Every element must carry exactly the availability/label metadata the frontend needs.
    for choice in choices:
        assert choice.keys() >= SECTION_LIST_CHOICE_KEYS

    all_sections = next(choice for choice in choices if choice["name"] == "all")
    assert all_sections == {
        "availability": "available",
        "available": True,
        "description": "Apical, basal, somatic, and axonal sections.",
        "display_order": 0,
        "label": "All sections",
        "name": "all",
    }


def test_section_list_choices_valid_property_names_passes():
    # The real, generated schema must expose the section-list key enum on `propertyNames`.
    validate_section_list_property_names(
        _mechanism_regions_schema(), SECTION_LIST_CHOICES_FIELD, SECTION_LIST_CHOICES_BLOCK
    )


def test_mechanism_regions_property_names_enum_lists_section_list_names():
    schema = _mechanism_regions_schema()
    property_names = schema["propertyNames"]
    if property_names_ref := property_names.get("$ref"):
        property_names = resolve_ref(openapi_schema, property_names_ref)

    assert property_names["enum"] == [
        "all",
        "alldend",
        "somadend",
        "allnoaxon",
        "somaxon",
        "allact",
        "somatic",
        "basal",
        "apical",
        "axonal",
        "myelinated",
    ]


def test_section_list_choices_rejects_missing_property_names():
    schema = _mechanism_regions_schema()
    schema.pop("propertyNames", None)
    with pytest.raises(ValueError, match="must expose a 'propertyNames' schema"):
        validate_section_list_choices(
            schema, SECTION_LIST_CHOICES_FIELD, SECTION_LIST_CHOICES_BLOCK
        )


def test_section_list_property_names_rejects_missing_enum():
    schema = _mechanism_regions_schema()
    schema["propertyNames"] = {"type": "string"}
    with pytest.raises(ValueError, match="'propertyNames' must expose an 'enum'"):
        validate_section_list_property_names(
            schema, SECTION_LIST_CHOICES_FIELD, SECTION_LIST_CHOICES_BLOCK
        )


def test_section_list_property_names_rejects_enum_choices_mismatch():
    schema = _mechanism_regions_schema()
    schema["propertyNames"] = {"type": "string", "enum": ["all"]}
    with pytest.raises(ValueError, match="must match the section-list 'choices' names"):
        validate_section_list_property_names(
            schema, SECTION_LIST_CHOICES_FIELD, SECTION_LIST_CHOICES_BLOCK
        )


def test_section_list_choices_rejects_missing_choices():
    schema = _mechanism_regions_schema()
    schema.pop("choices", None)
    with pytest.raises(ValueError, match="must expose a 'choices' list"):
        validate_section_list_choices(schema, SECTION_LIST_CHOICES_FIELD, "ref")


def test_section_list_choices_rejects_non_list():
    schema = _mechanism_regions_schema()
    schema["choices"] = {"name": "all"}
    with pytest.raises(TypeError, match="'choices' must be a list"):
        validate_section_list_choices(schema, SECTION_LIST_CHOICES_FIELD, "ref")


def test_section_list_choices_rejects_element_missing_keys():
    schema = _mechanism_regions_schema()
    schema["choices"] = [{"name": "all", "label": "All sections"}]
    with pytest.raises(ValueError, match="missing required keys"):
        validate_section_list_choices(schema, SECTION_LIST_CHOICES_FIELD, "ref")


def test_section_list_choices_rejects_wrong_element_type():
    schema = _mechanism_regions_schema()
    schema["choices"] = [
        {
            "availability": "available",
            "available": "yes",  # must be a boolean
            "description": "Apical, basal, somatic, and axonal sections.",
            "display_order": 0,
            "label": "All sections",
            "name": "all",
        }
    ]
    with pytest.raises(TypeError, match="choice 'available' must be a bool"):
        validate_section_list_choices(schema, SECTION_LIST_CHOICES_FIELD, "ref")


def test_global_parameters_rejects_missing_default():
    schema = copy.deepcopy(openapi_schema["components"]["schemas"]["EModelOptimisationParameters"])
    del schema["properties"]["global_parameters"]["default"]
    with pytest.raises(ValueError, match="global_parameters must have a 'default'"):
        validate_emodel_optimisation_parameters(
            schema, "emodel_optimisation_parameters", "ref", "config_ref", {}
        )


# ---------------------------------------------------------------------------
# Targeted tests for the `distance_function_input` UI element validator.
# ---------------------------------------------------------------------------

# ExponentialNaDendDistanceDependentDistribution.function uses
# UIElement.DISTANCE_FUNCTION_INPUT with max_length=MAX_DISTANCE_FUNCTION_LENGTH.
DISTANCE_FUNCTION_BLOCK = "ExponentialNaDendDistanceDependentDistribution"
DISTANCE_FUNCTION_FIELD = "function"


def _distance_function_schema() -> dict:
    """Return a deep copy of the real `distance_function_input` field schema."""
    return copy.deepcopy(
        openapi_schema["components"]["schemas"][DISTANCE_FUNCTION_BLOCK]["properties"][
            DISTANCE_FUNCTION_FIELD
        ]
    )


def test_distance_function_input_valid_schema_passes():
    schema = _distance_function_schema()
    assert schema.get("maxLength") == MAX_DISTANCE_FUNCTION_LENGTH
    validate_distance_function_input(schema, DISTANCE_FUNCTION_FIELD, DISTANCE_FUNCTION_BLOCK)


def test_distance_function_input_rejects_missing_max_length():
    schema = _distance_function_schema()
    del schema["maxLength"]
    with pytest.raises(ValidationError, match="max_length=MAX_DISTANCE_FUNCTION_LENGTH"):
        validate_distance_function_input(schema, DISTANCE_FUNCTION_FIELD, "ref")


def test_distance_function_input_rejects_wrong_max_length():
    schema = _distance_function_schema()
    schema["maxLength"] = MAX_DISTANCE_FUNCTION_LENGTH + 1
    with pytest.raises(ValidationError, match="max_length=MAX_DISTANCE_FUNCTION_LENGTH"):
        validate_distance_function_input(schema, DISTANCE_FUNCTION_FIELD, "ref")


def test_distance_function_input_rejects_nullable_schema():
    # The non-nullable validator must reject an anyOf (`str | None`) schema; that is the
    # nullable element's job.
    schema: dict[str, Any] = {
        "anyOf": [{"type": "string", "maxLength": MAX_DISTANCE_FUNCTION_LENGTH}, {"type": "null"}],
        SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT,
    }
    with pytest.raises(ValidationError, match="plain 'string'"):
        validate_distance_function_input(schema, DISTANCE_FUNCTION_FIELD, "ref")


# ---------------------------------------------------------------------------
# Targeted tests for the `distance_function_input_nullable` UI element validator.
# ---------------------------------------------------------------------------

# DistanceDependentDistribution.function (the abstract base) uses
# UIElement.DISTANCE_FUNCTION_INPUT_NULLABLE: a `str | None` whose string branch carries
# max_length. The base is never a schema component, so build the schema explicitly.


def _nullable_distance_function_schema() -> dict:
    return {
        "anyOf": [{"type": "string", "maxLength": MAX_DISTANCE_FUNCTION_LENGTH}, {"type": "null"}],
        SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT_NULLABLE,
    }


def test_distance_function_input_nullable_valid_schema_passes():
    validate_distance_function_input_nullable(
        _nullable_distance_function_schema(), DISTANCE_FUNCTION_FIELD, "ref"
    )


def test_distance_function_input_nullable_rejects_missing_max_length():
    schema = _nullable_distance_function_schema()
    del schema["anyOf"][0]["maxLength"]
    with pytest.raises(ValidationError, match="max_length=MAX_DISTANCE_FUNCTION_LENGTH"):
        validate_distance_function_input_nullable(schema, DISTANCE_FUNCTION_FIELD, "ref")


def test_distance_function_input_nullable_rejects_wrong_max_length():
    schema = _nullable_distance_function_schema()
    schema["anyOf"][0]["maxLength"] = MAX_DISTANCE_FUNCTION_LENGTH + 1
    with pytest.raises(ValidationError, match="max_length=MAX_DISTANCE_FUNCTION_LENGTH"):
        validate_distance_function_input_nullable(schema, DISTANCE_FUNCTION_FIELD, "ref")


def test_distance_function_input_nullable_rejects_string_not_first():
    schema: dict[str, Any] = {
        "anyOf": [{"type": "null"}, {"type": "string", "maxLength": MAX_DISTANCE_FUNCTION_LENGTH}],
        SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT_NULLABLE,
    }
    with pytest.raises(ValidationError, match="first anyOf branch"):
        validate_distance_function_input_nullable(schema, DISTANCE_FUNCTION_FIELD, "ref")


def test_distance_function_input_nullable_rejects_plain_string():
    # A plain non-nullable string must be rejected; that is the non-nullable element's job.
    schema: dict[str, Any] = {
        "type": "string",
        "maxLength": MAX_DISTANCE_FUNCTION_LENGTH,
        SchemaKey.UI_ELEMENT: UIElement.DISTANCE_FUNCTION_INPUT_NULLABLE,
    }
    with pytest.raises(ValidationError, match="anyOf"):
        validate_distance_function_input_nullable(schema, DISTANCE_FUNCTION_FIELD, "ref")
