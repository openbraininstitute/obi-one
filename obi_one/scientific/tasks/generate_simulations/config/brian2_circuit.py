"""Configuration for generating Brian2-compatible SONATA simulation configs.

Mirrors ``CircuitSimulationScanConfig`` but restricts blocks to those
supported by the Brian2 simulator with point neuron models.
"""

import logging
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.generate_simulations.config.base import (
    DEFAULT_NODE_SET_NAME,
    DEFAULT_TIMESTAMPS_NAME,
    BlockGroup,
    SimulationScanConfig,
    SimulationSingleConfigMixin,
)
from obi_one.scientific.unions.unions_brian2 import (
    Brian2CircuitStimulusUnion,
    Brian2RecordingUnion,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    SimulationNeuronSetUnion,
)
from obi_one.scientific.unions.unions_recordings import RecordingReference
from obi_one.scientific.unions.unions_stimuli import StimulusReference
from obi_one.scientific.unions.unions_timestamps import TimestampsReference

L = logging.getLogger(__name__)

Brian2CircuitDiscriminator = Annotated[Circuit | CircuitFromID, Field(discriminator="type")]

BRIAN2_TARGET_SIMULATOR = "BRIAN2"


class Brian2CircuitSimulationScanConfig(SimulationScanConfig):
    """Configuration for generating Brian2-targeted SONATA simulation configs.

    Only exposes stimulus, recording, and neuron set types that are
    compatible with Brian2 point neuron models. The generated
    ``simulation_config.json`` will have ``target_simulator: "BRIAN2"``.
    """

    single_coord_class_name: ClassVar[str] = "Brian2CircuitSimulationSingleConfig"
    name: ClassVar[str] = "Brian2 Simulation Campaign"
    description: ClassVar[str] = "Brian2-targeted SONATA simulation campaign"

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            BlockGroup.EVENTS_GROUP,
        ],
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: {
            NeuronSetReference.__name__: DEFAULT_NODE_SET_NAME,
            TimestampsReference.__name__: DEFAULT_TIMESTAMPS_NAME,
        },
    }

    neuron_sets: dict[str, SimulationNeuronSetUnion] = Field(
        default_factory=dict,
        description="Neuron sets for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
            SchemaKey.SINGULAR_NAME: "Neuron Set",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    class Initialize(SimulationScanConfig.Initialize):
        """Initialization parameters for a Brian2 circuit simulation."""

        circuit: Brian2CircuitDiscriminator | list[Brian2CircuitDiscriminator] = Field(
            title="Circuit",
            description="Circuit to simulate.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER},
        )
        node_set: NeuronSetReference | None = Field(
            default=None,
            title="Neuron Set",
            description="Neuron set to simulate.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
                SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
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

    stimuli: dict[str, Brian2CircuitStimulusUnion] = Field(
        default_factory=dict,
        title="Stimuli",
        description="Brian2-compatible stimuli for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: StimulusReference.__name__,
            SchemaKey.SINGULAR_NAME: "Stimulus",
            SchemaKey.GROUP: BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    recordings: dict[str, Brian2RecordingUnion] = Field(
        default_factory=dict,
        description="Brian2-compatible recordings for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: RecordingReference.__name__,
            SchemaKey.SINGULAR_NAME: "Recording",
            SchemaKey.GROUP: BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )


class Brian2CircuitSimulationSingleConfig(
    Brian2CircuitSimulationScanConfig, SimulationSingleConfigMixin
):
    """Only allows single values."""
