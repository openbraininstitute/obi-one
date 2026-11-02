"""Tests for neuronal-manipulation PROPERTY_ENDPOINTS metadata across scan configs."""

from obi_one.core.schema import SchemaKey
from obi_one.scientific.blocks.neuronal_manipulations.neuronal_manipulations import (
    ByNeuronMechanismVariableNeuronalManipulation,
    BySectionListMechanismVariableNeuronalManipulation,
    CircuitByNeuronMechanismVariableNeuronalManipulation,
    CircuitBySectionListMechanismVariableNeuronalManipulation,
)
from obi_one.scientific.library.entity_property_types import (
    CircuitMappedProperties,
    MappedPropertiesGroup,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron import (
    neuron_me_model_with_synapses,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationScanConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (
    MEModelSimulationScanConfig,
)

CIRCUIT_ENDPOINT = "/circuit-neuronal-manipulation-properties-by-neuron-set"
MEMODEL_ENDPOINT = "/memodel-neuronal-manipulation-properties"


def _modification_schema(block_cls):
    schema = block_cls.model_json_schema()
    return schema["properties"]["modification"]


def test_memodel_blocks_use_neuronal_manipulation_group():
    """MEModel manipulation blocks must use the NeuronalManipulation property group."""
    for block_cls in (
        BySectionListMechanismVariableNeuronalManipulation,
        ByNeuronMechanismVariableNeuronalManipulation,
    ):
        modification = _modification_schema(block_cls)
        assert modification[SchemaKey.PROPERTY_GROUP] == MappedPropertiesGroup.NEURONAL_MANIPULATION
        assert (
            modification[SchemaKey.PROPERTY]
            == CircuitMappedProperties.MECHANISM_VARIABLES_BY_ION_CHANNEL
        )
        assert SchemaKey.PROPERTY_SOURCE_FIELD not in modification


def test_circuit_blocks_use_neuronal_manipulation_group_with_source_field():
    """Circuit manipulation blocks must use NeuronalManipulation and a neuron_set source field."""
    for block_cls in (
        CircuitBySectionListMechanismVariableNeuronalManipulation,
        CircuitByNeuronMechanismVariableNeuronalManipulation,
    ):
        modification = _modification_schema(block_cls)
        assert modification[SchemaKey.PROPERTY_GROUP] == MappedPropertiesGroup.NEURONAL_MANIPULATION
        assert (
            modification[SchemaKey.PROPERTY]
            == CircuitMappedProperties.MECHANISM_VARIABLES_BY_ION_CHANNEL
        )
        assert modification[SchemaKey.PROPERTY_SOURCE_FIELD] == "neuron_set"


def test_memodel_config_maps_neuronal_manipulation_to_memodel_endpoint():
    schema = MEModelSimulationScanConfig.model_json_schema()
    property_endpoints = schema[SchemaKey.PROPERTY_ENDPOINTS]
    assert property_endpoints[MappedPropertiesGroup.NEURONAL_MANIPULATION] == MEMODEL_ENDPOINT
    assert property_endpoints[MappedPropertiesGroup.CIRCUIT] == (
        "/mapped-circuit-properties/{circuit_id}"
    )


def test_circuit_config_maps_neuronal_manipulation_to_circuit_endpoint():
    schema = CircuitSimulationScanConfig.model_json_schema()
    property_endpoints = schema[SchemaKey.PROPERTY_ENDPOINTS]
    assert property_endpoints[MappedPropertiesGroup.NEURONAL_MANIPULATION] == CIRCUIT_ENDPOINT
    assert property_endpoints[MappedPropertiesGroup.CIRCUIT] == (
        "/mapped-circuit-properties/{circuit_id}"
    )


def test_memodel_with_synapses_config_maps_neuronal_manipulation_to_circuit_endpoint():
    config_cls = neuron_me_model_with_synapses.MEModelWithSynapsesCircuitSimulationScanConfig
    schema = config_cls.model_json_schema()
    property_endpoints = schema[SchemaKey.PROPERTY_ENDPOINTS]
    assert property_endpoints[MappedPropertiesGroup.NEURONAL_MANIPULATION] == CIRCUIT_ENDPOINT
