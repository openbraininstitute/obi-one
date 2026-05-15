import logging
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.neuron_sets.base import AbstractNeuronSet
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.entity_property_types import (
    CircuitMappedProperties,
    MappedPropertiesGroup,
)

L = logging.getLogger(__name__)

CircuitNode = Annotated[str, Field(min_length=1)]
NodeSetType = CircuitNode | list[CircuitNode]


class PredefinedNeuronSet(AbstractNeuronSet):
    """Use an existing node set already defined in the circuit's node sets file."""

    title: ClassVar[str] = "Predefined Neuron Set"

    node_set: NodeSetType = Field(
        title="Node Set",
        description="Name of the node set to use.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENTITY_PROPERTY_DROPDOWN_SWEEP,
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitMappedProperties.NODE_SET,
        },
    )

    def check_node_set(self, circuit: Circuit, _population: str) -> None:
        if self.node_set not in circuit.node_sets:
            msg = (
                f"Node set '{self.node_set}' not found in circuit '{circuit.name}'. "
                f"Available node sets: {', '.join(circuit.node_sets)}"
            )
            raise ValueError(msg)

    def _get_expression(self, circuit: Circuit, population: str) -> list:  # ty:ignore[invalid-method-override]
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_node_set(circuit, population)
        return [self.node_set]
