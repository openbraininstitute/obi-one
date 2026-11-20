import pytest
from pydantic import ValidationError

from obi_one.core.info import Info
from obi_one.scientific.blocks.morphology_locations.random import RandomMorphologyLocations
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram.block import (
    ExcitatoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.from_id.circuit_from_id import MEModelWithSynapsesCircuitFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.entity_property_types import MappedPropertiesGroup
from obi_one.scientific.tasks.build_synaptome.blocks import SynapticModelPlacer
from obi_one.scientific.tasks.build_synaptome.config import (
    MEModelSynapticModelPlacementScanConfig,
    MEModelSynapticModelPlacementSingleConfig,
)
from obi_one.scientific.unions_and_references.morphology_locations import (
    MorphologyLocationsReference,
)
from obi_one.scientific.unions_and_references.synaptic_models import (
    SynapticModelReference,
)


def test_memodel_is_supplied_through_initialize_block():
    config = MEModelSynapticModelPlacementScanConfig(
        info=Info(campaign_name="test", campaign_description="test"),
        initialize=MEModelSynapticModelPlacementScanConfig.Initialize(
            me_model=MEModelFromID(id_str="me-model-id")
        ),
    )

    assert config.initialize.me_model.id_str == "me-model-id"
    assert not hasattr(config, "me_model")

    single_config = config.cast_to_single_coord()
    assert isinstance(single_config, MEModelSynapticModelPlacementSingleConfig)
    assert single_config.initialize.me_model.id_str == "me-model-id"


def test_schema_uses_initialize_instead_of_memodel_selection():
    schema = MEModelSynapticModelPlacementScanConfig.model_json_schema()

    assert "initialize" in schema["properties"]
    assert "me_model" not in schema["properties"]
    assert all("MEModelSelection" not in definition for definition in schema["$defs"])
    initialize_schema = schema["$defs"]["Initialize"]
    assert initialize_schema["properties"]["me_model"]["ui_element"] == "model_identifier"


def test_input_schema_lists_exactly_the_accepted_entity_types():
    """An agent reading the schema must be able to tell which entities can be the input."""
    schema = MEModelSynapticModelPlacementScanConfig.model_json_schema()
    input_schema = schema["$defs"]["Initialize"]["properties"]["me_model"]

    assert {branch["$ref"].rsplit("/", 1)[-1] for branch in input_schema["anyOf"]} == {
        "MEModelFromID",
        "MEModelWithSynapsesCircuitFromID",
    }


@pytest.mark.parametrize("entity_type", [MEModelFromID, MEModelWithSynapsesCircuitFromID])
def test_input_is_read_as_the_kind_of_entity_it_names(entity_type):
    initialize = MEModelSynapticModelPlacementScanConfig.Initialize.model_validate(
        {"me_model": {"type": entity_type.__name__, "id_str": "entity-id"}}
    )

    assert type(initialize.me_model) is entity_type
    assert initialize.me_model.id_str == "entity-id"


def test_an_input_without_a_type_is_read_as_an_me_model():
    """Configs saved when the input could only be an ME-model may have no `type`."""
    initialize = MEModelSynapticModelPlacementScanConfig.Initialize.model_validate(
        {"me_model": {"id_str": "me-model-id"}}
    )

    assert type(initialize.me_model) is MEModelFromID


def test_input_of_another_entity_type_is_rejected():
    with pytest.raises(ValidationError, match="Input should be"):
        MEModelSynapticModelPlacementScanConfig.Initialize.model_validate(
            {"me_model": {"type": "CircuitFromID", "id_str": "entity-id"}}
        )


def test_placement_strategy_is_a_reference_to_root_morphology_locations():
    schema = MEModelSynapticModelPlacementScanConfig.model_json_schema()

    property_endpoints = schema["property_endpoints"]
    assert property_endpoints[MappedPropertiesGroup.CIRCUIT] == (
        "/mapped-circuit-properties/{circuit_id}"
    )
    assert property_endpoints[MappedPropertiesGroup.MORPHOLOGY] == (
        "/mapped-morphology-properties/{circuit_id}"
    )

    locations_schema = schema["properties"]["morphology_locations"]
    assert locations_schema["ui_element"] == "block_dictionary"
    assert locations_schema["reference_types"] == [MorphologyLocationsReference.__name__]

    placement_schema = schema["$defs"]["SynapticModelPlacer"]["properties"]["placement_strategy"]
    assert placement_schema["ui_element"] == "reference"
    assert placement_schema["reference_types"] == [MorphologyLocationsReference.__name__]


def test_placement_strategy_reference_is_resolved():
    placement_strategy = RandomMorphologyLocations(
        number_of_locations=4,
        section_types=(3,),
        random_seed=11,
    )
    config = MEModelSynapticModelPlacementScanConfig(
        info=Info(campaign_name="test", campaign_description="test"),
        initialize=MEModelSynapticModelPlacementScanConfig.Initialize(
            me_model=MEModelFromID(id_str="me-model-id")
        ),
        synaptic_models={"exc": ExcitatoryTsodyksMarkramSynapticModel()},
        morphology_locations={"basal_locations": placement_strategy},
        synapse_groups={
            "basal": SynapticModelPlacer(
                synaptic_model=SynapticModelReference(
                    block_dict_name="synaptic_models",
                    block_name="exc",
                ),
                placement_strategy=MorphologyLocationsReference(
                    block_dict_name="morphology_locations",
                    block_name="basal_locations",
                ),
            )
        },
    )

    reference = config.synapse_groups["basal"].placement_strategy
    assert reference.block is config.morphology_locations["basal_locations"]


def test_synapse_groups_use_synapse_group_singular_name():
    schema = MEModelSynapticModelPlacementScanConfig.model_json_schema()

    assert schema["properties"]["synapse_groups"]["singular_name"] == "Synapse Group"


def test_morphology_location_reference_offers_grouped_blocks():
    """The grouped blocks are selectable through the morphology-location reference."""
    allowed = set(MorphologyLocationsReference.model_json_schema()["allowed_block_types"])

    assert "RandomGroupedMorphologyLocations" in allowed
    assert "ClusteredGroupedMorphologyLocations" in allowed


def test_the_form_group_is_named_for_the_postsynaptic_neuron():
    schema = MEModelSynapticModelPlacementScanConfig.model_json_schema()

    assert "Postsynaptic neuron" in schema["group_order"]
    assert "ME-model" not in schema["group_order"]
    assert schema["properties"]["initialize"]["group"] == "Postsynaptic neuron"
