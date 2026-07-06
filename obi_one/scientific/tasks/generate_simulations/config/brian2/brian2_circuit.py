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
    DEFAULT_TIMESTAMPS_NAME,
    BlockGroup,
    SimulationSingleConfigMixin,
)
from obi_one.scientific.tasks.generate_simulations.config.brian2.brian2_base import (
    Brian2SimulationScanConfig,
)
from obi_one.scientific.unions.unions_combined_neuron_sets import (
    POINT_NEURON_SETS_REFERENCE_TYPES,
    POINT_NEURON_SETS_REFERENCE_UNION,
    Brian2SimulationNeuronSetUnion,
)
from obi_one.scientific.unions.unions_neuron_sets import AtomicPointNeuronSetReference
from obi_one.scientific.unions.unions_stimuli import (
    Brian2CircuitStimulusUnion,
    StimulusReference,
)
from obi_one.scientific.unions.unions_timestamps import TimestampsReference

L = logging.getLogger(__name__)

Brian2CircuitDiscriminator = Annotated[Circuit | CircuitFromID, Field(discriminator="type")]


class Brian2CircuitSimulationScanConfig(Brian2SimulationScanConfig):
    """Configuration for generating Brian2-targeted SONATA simulation configs.

    Only exposes stimulus, recording, and neuron set types that are
    compatible with Brian2 point neuron models. The generated
    ``simulation_config.json`` will have ``target_simulator: "Brian2"``.
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
        ],
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: {
            AtomicPointNeuronSetReference.__name__: (
                Brian2SimulationScanConfig.default_node_set_name,
            ),
            TimestampsReference.__name__: DEFAULT_TIMESTAMPS_NAME,
        },
    }

    class Initialize(Brian2SimulationScanConfig.Initialize):
        """Initialization parameters for a Brian2 circuit simulation."""

        circuit: Brian2CircuitDiscriminator | list[Brian2CircuitDiscriminator] = Field(
            title="Circuit",
            description="Circuit to simulate.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
                SchemaKey.PARAMETER_ORDER_PRIORITY: 100,
            },
        )
        node_set: POINT_NEURON_SETS_REFERENCE_UNION | None = Field(
            default=None,
            title="Neuron Set",
            description="Neuron set to simulate.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
                SchemaKey.REFERENCE_TYPES: POINT_NEURON_SETS_REFERENCE_TYPES,
                SchemaKey.PARAMETER_ORDER_PRIORITY: 99,
                SchemaKey.UI_HIDDEN: True,
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
            SchemaKey.REFERENCE_TYPES: [StimulusReference.__name__],
            SchemaKey.SINGULAR_NAME: "Stimulus",
            SchemaKey.GROUP: BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    neuron_sets: dict[str, Brian2SimulationNeuronSetUnion] = Field(
        default_factory=dict,
        description="Neuron sets for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: POINT_NEURON_SETS_REFERENCE_TYPES,
            SchemaKey.SINGULAR_NAME: "Neuron Set",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class Brian2CircuitSimulationSingleConfig(
    Brian2CircuitSimulationScanConfig, SimulationSingleConfigMixin
):
    """Only allows single values."""
