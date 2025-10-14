
class PredefinedNeuronSet(AbstractNeuronSet):
    """Use an existing node set already defined in the circuit's node sets file."""

    title: ClassVar[str] = "Predefined Neuron Set"

    node_set: Annotated[
        NodeSetType, Field(min_length=1, entity_property_type=CircuitPropertyType.NODE_SET)
    ]

    def check_node_set(self, circuit: Circuit, _population: str) -> None:
        if self.node_set not in circuit.node_sets:
            msg = f"Node set '{self.node_set}' not found in circuit '{circuit}'!"
            raise ValueError(msg)

    def _get_expression(self, circuit: Circuit, population: str) -> list:
        """Returns the SONATA node set expression (w/o subsampling)."""
        self.check_node_set(circuit, population)
        return [self.node_set]