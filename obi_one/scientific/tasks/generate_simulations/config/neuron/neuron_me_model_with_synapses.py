"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, line-too-long]

from obi_one_lazy.scientific.tasks.generate_simulations.config.neuron.neuron_me_model_with_synapses import (
    ALL_NEURON_SETS_REFERENCE_TYPES,
    Annotated,
    BlockGroup,
    CircuitSimulationScanConfig,
    ClassVar,
    Field,
    L,
    MappedPropertiesGroup,
    MEModelWithSynapsesCircuit,
    MEModelWithSynapsesCircuitDiscriminator,
    MEModelWithSynapsesCircuitFromID,
    MEModelWithSynapsesCircuitSimulationScanConfig,
    MEModelWithSynapsesCircuitSimulationSingleConfig,
    MorphologyLocationsReference,
    MorphologyLocationUnion,
    NEURONMEModelWithSynapsesNeuronSetUnion,
    SchemaKey,
    SimulationSingleConfigMixin,
    UIElement,
    logging,
)
