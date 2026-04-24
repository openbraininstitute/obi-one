import logging
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.from_id.circuit_from_id import (
    CircuitFromID,
)
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.generate_simulations.config.base import (
    DEFAULT_NODE_SET_NAME,
    DEFAULT_TIMESTAMPS_NAME,
    BlockGroup,
    SimulationScanConfig,
    SimulationSingleConfigMixin,
)
from obi_one.scientific.unions.unions_manipulations import (
    SynapticManipulationsReference,
    SynapticManipulationsUnion,
)
from obi_one.scientific.unions.unions_neuron_sets_2 import (
    ALL_NEURON_SETS_REFERENCE_TYPES,
    AllNeuronSet2Union,
    AllNeuronSetUnion,
    BiophysicalAndPointNeuronSet2Reference,
    NeuronSet2Reference,
)
from obi_one.scientific.unions.unions_stimuli import (
    CircuitStimulusUnion,
    StimulusReference,
)
from obi_one.scientific.unions.unions_timestamps import (
    TimestampsReference,
)

L = logging.getLogger(__name__)

CircuitDiscriminator = Annotated[Circuit | CircuitFromID, Field(discriminator="type")]


class CircuitSimulationScanConfig(SimulationScanConfig):
    """CircuitSimulationScanConfig."""

    single_coord_class_name: ClassVar[str] = "CircuitSimulationSingleConfig"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            BlockGroup.CIRCUIT_MANIPULATIONS_GROUP,
            BlockGroup.EVENTS_GROUP,
        ],
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: {
            NeuronSet2Reference.__name__: DEFAULT_NODE_SET_NAME,
            BiophysicalAndPointNeuronSet2Reference.__name__: DEFAULT_NODE_SET_NAME,
            TimestampsReference.__name__: DEFAULT_TIMESTAMPS_NAME,
        },
    }

    neuron_sets: dict[str, AllNeuronSetUnion] = Field(
        default_factory=dict,
        title="Neuron Sets",
        description="Neuron sets for the simulation (new version).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: ALL_NEURON_SETS_REFERENCE_TYPES,
            SchemaKey.SINGULAR_NAME: "Neuron Set",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    synaptic_manipulations: dict[str, SynapticManipulationsUnion] = Field(
        default_factory=dict,
        description="Synaptic manipulations for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [SynapticManipulationsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Synaptic Manipulation",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_MANIPULATIONS_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    class Initialize(SimulationScanConfig.Initialize):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit",
            description="Circuit to simulate.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER},
        )
        node_set: BiophysicalAndPointNeuronSet2Reference | None = Field(
            default=None,
            title="Neuron Set",
            description="Neuron set to simulate.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
                SchemaKey.REFERENCE_TYPES: ALL_NEURON_SETS_REFERENCE_TYPES,
            },
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    stimuli: dict[str, CircuitStimulusUnion] = Field(
        default_factory=dict,
        title="Stimuli",
        description="Stimuli for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [StimulusReference.__name__],
            SchemaKey.SINGULAR_NAME: "Stimulus",
            SchemaKey.GROUP: BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class CircuitSimulationSingleConfig(CircuitSimulationScanConfig, SimulationSingleConfigMixin):
    """Only allows single values."""
