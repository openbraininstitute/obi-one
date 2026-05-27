import logging

from pydantic import Field
from typing import ClassVar

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BlockGroup,
)
from obi_one.scientific.tasks.generate_simulations.config.circuit import (
    BaseCircuitSimulationScanConfig,
    CircuitDiscriminator,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_base import (
    NeuronSimulationScanConfig,
)
from obi_one.scientific.unions.unions_distributions import (
    AllDistributionsReference,
    AllDistributionsUnion,
)
from obi_one.scientific.unions.unions_manipulations import (
    SynapticManipulationsReference,
    SynapticManipulationsUnion,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
)
from obi_one.scientific.unions.unions_stimuli import (
    CircuitStimulusUnion,
    StimulusReference,
)
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BlockGroup,
    SimulationSingleConfigMixin,
)

__all__ = [
    "CircuitDiscriminator",
    "CircuitSimulationScanConfig",
    "CircuitSimulationSingleConfig",
]

L = logging.getLogger(__name__)


class CircuitSimulationScanConfig(NeuronSimulationScanConfig, BaseCircuitSimulationScanConfig):
    """CircuitSimulationScanConfig."""

    single_coord_class_name: ClassVar[str] = "CircuitSimulationSingleConfig"

    class Initialize(
        NeuronSimulationScanConfig.Initialize, BaseCircuitSimulationScanConfig.Initialize 
    ):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
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

    synaptic_manipulations: dict[str, SynapticManipulationsUnion] = Field(
        default_factory=dict,
        description="Synaptic manipulations for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: SynapticManipulationsReference.__name__,
            SchemaKey.SINGULAR_NAME: "Synaptic Manipulation",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_MANIPULATIONS_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    stimuli: dict[str, CircuitStimulusUnion] = Field(
        default_factory=dict,
        title="Stimuli",
        description="Stimuli for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: StimulusReference.__name__,
            SchemaKey.SINGULAR_NAME: "Stimulus",
            SchemaKey.GROUP: BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    distributions: dict[str, AllDistributionsUnion] = Field(
        default_factory=dict,
        title="Distributions",
        description="Distributions used by stimuli (e.g. inter-spike interval distributions).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
            SchemaKey.SINGULAR_NAME: "Distribution",
            SchemaKey.GROUP: BlockGroup.DISTRIBUTIONS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class CircuitSimulationSingleConfig(CircuitSimulationScanConfig, SimulationSingleConfigMixin):
    """Only allows single values."""
