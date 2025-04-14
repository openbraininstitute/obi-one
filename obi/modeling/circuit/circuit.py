from obi.modeling.core.block import Block
import bluepysnap as snap
import os

class Circuit(Block):
    """
    Class representing a circuit, i.e., pointing to a SONATA config.
    """
    path: str
    name: str

    def __init__(self, name, path):
        super().__init__(name=name, path=path)
        _c = snap.Circuit(self.path)  # Basic check: Try to load the SONATA circuit w/o error

    def __repr__(self):
        return self.name

    @property
    def sonata_circuit(self):
        """Provide access to SONATA circuit object."""
        return snap.Circuit(self.path)

    @property
    def node_population_names(self):
        """Returns node population names."""
        return self.sonata_circuit.nodes.population_names

    @property
    def edge_population_names(self):
        """Returns edge population names."""
        return self.sonata_circuit.edges.population_names
