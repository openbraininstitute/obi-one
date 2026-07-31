import pytest

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.morphology_locations.random import (
    RandomMorphologyLocations,
)
from obi_one.scientific.library.entity_property_types import MappedPropertiesGroup
from obi_one.scientific.tasks.generate_simulations.config.neuron import (
    neuron_me_model_with_synapses,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationScanConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (
    MEModelSimulationScanConfig,
)
from obi_one.scientific.tasks.morphology_locations import MorphologyLocationsScanConfig

from .validate_block import validate_morphology_section_type_selection


def test_morphology_section_type_selection_schema():
    schema = RandomMorphologyLocations.model_json_schema()["properties"]["section_types"]

    assert schema[SchemaKey.UI_ELEMENT] == UIElement.MORPHOLOGY_SECTION_TYPE_SELECTION
    validate_morphology_section_type_selection(
        schema,
        "section_types",
        "#/components/schemas/RandomMorphologyLocations",
    )


def test_morphology_section_type_selection_rejects_invalid_mapped_property():
    schema = RandomMorphologyLocations.model_json_schema()["properties"]["section_types"]
    schema[SchemaKey.PROPERTY] = "NodeSet"

    with pytest.raises(ValueError, match="property must be one of"):
        validate_morphology_section_type_selection(
            schema,
            "section_types",
            "#/components/schemas/RandomMorphologyLocations",
        )


def test_morphology_endpoint_is_available_for_neuron_simulation_configs():
    endpoint = "/mapped-morphology-properties/{circuit_id}"

    for config_class in (
        CircuitSimulationScanConfig,
        MEModelSimulationScanConfig,
        neuron_me_model_with_synapses.MEModelWithSynapsesCircuitSimulationScanConfig,
    ):
        schema = config_class.model_json_schema()
        property_endpoints = schema[SchemaKey.PROPERTY_ENDPOINTS]
        assert property_endpoints[MappedPropertiesGroup.MORPHOLOGY] == endpoint
        assert property_endpoints[MappedPropertiesGroup.CIRCUIT] == (
            "/mapped-circuit-properties/{circuit_id}"
        )
        assert schema[SchemaKey.UI_ENABLED] is True
        assert schema[SchemaKey.GROUP_ORDER]
        assert schema[SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS]


def test_direct_morphology_uses_generic_endpoint_with_supported_placeholder():
    property_endpoints = MorphologyLocationsScanConfig.model_json_schema()[
        SchemaKey.PROPERTY_ENDPOINTS
    ]

    assert property_endpoints[MappedPropertiesGroup.MORPHOLOGY] == (
        "/mapped-morphology-properties/{morphology_id}"
    )
