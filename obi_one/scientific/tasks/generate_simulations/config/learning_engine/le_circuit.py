import logging
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.generate_simulations.config.base import (
    DEFAULT_DISTRIBUTION_NAME,
    DEFAULT_TIMESTAMPS_NAME,
    BlockGroup,
    CircuitFromID,
    SimulationSingleConfigMixin,
)
from obi_one.scientific.tasks.generate_simulations.config.learning_engine.le_base import (
    LearningEngineSimulationScanConfig,
)
from obi_one.scientific.unions.unions_combined_neuron_sets import (
    POINT_NEURON_SETS_REFERENCE_TYPES,
    POINT_NEURON_SETS_REFERENCE_UNION,
    LearningEngineNeuronSetUnion,
)
from obi_one.scientific.unions.unions_distributions import (
    AllDistributionsReference,
)
from obi_one.scientific.unions.unions_neuron_sets import PointNeuronSetReference
from obi_one.scientific.unions.unions_stimuli import (
    LearningEngineCircuitStimulusUnion,
    StimulusReference,
)
from obi_one.scientific.unions.unions_timestamps import TimestampsReference, TimestampsUnion

L = logging.getLogger(__name__)

CircuitDiscriminator = Annotated[Circuit | CircuitFromID, Field(discriminator="type")]


class LearningEngineCircuitSimulationScanConfig(LearningEngineSimulationScanConfig):
    """LearningEngineCircuitSimulationScanConfig."""

    single_coord_class_name: ClassVar[str] = "LearningEngineCircuitSimulationSingleConfig"

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            BlockGroup.EVENTS_GROUP,
        ],
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: {
            PointNeuronSetReference.__name__: (
                LearningEngineSimulationScanConfig.default_node_set_name
            ),
            TimestampsReference.__name__: DEFAULT_TIMESTAMPS_NAME,
            AllDistributionsReference.__name__: DEFAULT_DISTRIBUTION_NAME,
        },
    }

    class Initialize(LearningEngineSimulationScanConfig.Initialize):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
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

    stimuli: dict[str, LearningEngineCircuitStimulusUnion] = Field(
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

    neuron_sets: dict[str, LearningEngineNeuronSetUnion] = Field(
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

    timestamps: dict[str, TimestampsUnion] = Field(
        default_factory=dict,
        title="Timestamps",
        description="Timestamps for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [TimestampsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Timestamps",
            SchemaKey.GROUP: BlockGroup.EVENTS_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class LearningEngineCircuitSimulationSingleConfig(
    LearningEngineCircuitSimulationScanConfig, SimulationSingleConfigMixin
):
    """Only allows single values."""
