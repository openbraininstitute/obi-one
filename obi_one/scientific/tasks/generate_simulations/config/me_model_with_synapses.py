import logging
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.from_id.circuit_from_id import (
    MEModelWithSynapsesCircuitFromID,
)
from obi_one.scientific.library.memodel_circuit import MEModelWithSynapsesCircuit
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BlockGroup,
    SimulationScanConfig,
    SimulationSingleConfigMixin,
)
from obi_one.scientific.tasks.generate_simulations.config.circuit import CircuitSimulationScanConfig
from obi_one.scientific.unions.unions_neuron_sets_2 import (
    VirtualNeuronSetUnion,
    VirtualNeuronSetReference,
)

L = logging.getLogger(__name__)


MEModelWithSynapsesCircuitDiscriminator = Annotated[
    MEModelWithSynapsesCircuit | MEModelWithSynapsesCircuitFromID, Field(discriminator="type")
]


class MEModelWithSynapsesCircuitSimulationScanConfig(CircuitSimulationScanConfig):
    """MEModelWithSynapsesCircuitSimulationScanConfig."""

    single_coord_class_name: ClassVar[str] = "MEModelWithSynapsesCircuitSimulationSingleConfig"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    neuron_sets: dict[str, VirtualNeuronSetUnion] = Field(
        default_factory=dict,
        title="Neuron Sets",
        description="Neuron sets for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [VirtualNeuronSetReference.__name__],
            SchemaKey.SINGULAR_NAME: "Neuron Set",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    class Initialize(SimulationScanConfig.Initialize):
        circuit: (
            MEModelWithSynapsesCircuitDiscriminator | list[MEModelWithSynapsesCircuitDiscriminator]
        ) = Field(
            title="MEModel With Synapses",
            description="MEModel with synapses to simulate.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER},
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


class MEModelWithSynapsesCircuitSimulationSingleConfig(
    MEModelWithSynapsesCircuitSimulationScanConfig, SimulationSingleConfigMixin
):
    """Only allows single values."""
