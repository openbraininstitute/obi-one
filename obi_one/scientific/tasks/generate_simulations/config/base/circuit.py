import abc
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.from_id.circuit_from_id import (
    CircuitFromID,
)
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.generate_simulations.config.base.base import (
    BaseSimulationScanConfig,
    BlockGroup,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    SimulationNeuronSetUnion,
)

CircuitDiscriminator = Annotated[Circuit | CircuitFromID, Field(discriminator="type")]


class CircuitBaseSimulationScanConfig(BaseSimulationScanConfig, abc.ABC):
    """Circuit-specific simulation scan config (blocks, fields, and Initialize)."""

    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    class Initialize(BaseSimulationScanConfig.Initialize, abc.ABC):
        """Important to define the circuit here, even if overriden,
        so that it keeps its position in the schema.
        """

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
