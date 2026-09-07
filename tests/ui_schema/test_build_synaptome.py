from obi_one.core.info import Info
from obi_one.scientific.blocks.morphology_locations.random import RandomMorphologyLocations
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.entity_property_types import MappedPropertiesGroup
from obi_one.scientific.tasks.build_synaptome import (
    MEModelSynapticModelPlacementScanConfig,
    MEModelSynapticModelPlacementSingleConfig,
    SynapticModelPlacer,
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
