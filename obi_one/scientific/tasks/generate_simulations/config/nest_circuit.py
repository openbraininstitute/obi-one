"""Configuration for generating NEST-compatible SONATA simulation configs.

Mirrors ``CircuitSimulationScanConfig`` but restricts blocks to those
supported by the NEST simulator with point neuron models.
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
from obi_one.scientific.unions.unions_nest import (
    NestCircuitStimulusUnion,
    NestRecordingUnion,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    SimulationNeuronSetUnion,
)
from obi_one.scientific.unions.unions_recordings import RecordingReference
from obi_one.scientific.unions.unions_stimuli import StimulusReference
from obi_one.scientific.unions.unions_timestamps import TimestampsReference

L = logging.getLogger(__name__)

NestCircuitDiscriminator = Annotated[Circuit | CircuitFromID, Field(discriminator="type")]

NEST_TARGET_SIMULATOR = "NEST"


class NestCircuitSimulationScanConfig(SimulationScanConfig):
    """Configuration for generating NEST-targeted SONATA simulation configs.

    Only exposes stimulus, recording, and neuron set types that are
    compatible with NEST point neuron models.  The generated
    ``simulation_config.json`` will have ``target_simulator: "NEST"``.
    """

    single_coord_class_name: ClassVar[str] = "NestCircuitSimulationSingleConfig"
    name: ClassVar[str] = "NEST Simulation Campaign"
    description: ClassVar[str] = "NEST-targeted SONATA simulation campaign"

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
        """Initialization parameters for a NEST circuit simulation."""

        circuit: NestCircuitDiscriminator | list[NestCircuitDiscriminator] = Field(
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

    stimuli: dict[str, NestCircuitStimulusUnion] = Field(
        default_factory=dict,
        title="Stimuli",
        description="NEST-compatible stimuli for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: StimulusReference.__name__,
            SchemaKey.SINGULAR_NAME: "Stimulus",
            SchemaKey.GROUP: BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    recordings: dict[str, NestRecordingUnion] = Field(
        default_factory=dict,
        description="NEST-compatible recordings for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: RecordingReference.__name__,
            SchemaKey.SINGULAR_NAME: "Recording",
            SchemaKey.GROUP: BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )


class NestCircuitSimulationSingleConfig(
    NestCircuitSimulationScanConfig, SimulationSingleConfigMixin
):
    """Only allows single values."""
