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


def test_morphology_source_endpoint_is_limited_to_single_neuron_configs():
    endpoint = "/mapped-morphology-source-properties/{circuit_id}"

    for config_class in (
        MEModelSimulationScanConfig,
        neuron_me_model_with_synapses.MEModelWithSynapsesCircuitSimulationScanConfig,
    ):
        schema = config_class.model_json_schema()
        property_endpoints = schema[SchemaKey.PROPERTY_ENDPOINTS]
        assert property_endpoints[MappedPropertiesGroup.MORPHOLOGY_SOURCE] == endpoint
        assert property_endpoints[MappedPropertiesGroup.CIRCUIT] == (
            "/mapped-circuit-properties/{circuit_id}"
        )
        assert schema[SchemaKey.UI_ENABLED] is True
        assert schema[SchemaKey.GROUP_ORDER]
        assert schema[SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS]

    circuit_property_endpoints = CircuitSimulationScanConfig.model_json_schema()[
        SchemaKey.PROPERTY_ENDPOINTS
    ]
    assert MappedPropertiesGroup.MORPHOLOGY_SOURCE not in circuit_property_endpoints


def test_direct_morphology_uses_generic_source_endpoint_with_supported_placeholder():
    property_endpoints = MorphologyLocationsScanConfig.model_json_schema()[
        SchemaKey.PROPERTY_ENDPOINTS
    ]

    assert property_endpoints[MappedPropertiesGroup.MORPHOLOGY_SOURCE] == (
        "/mapped-morphology-source-properties/{morphology_id}"
    )
