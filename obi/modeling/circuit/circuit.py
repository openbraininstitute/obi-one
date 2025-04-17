from obi.modeling.core.base import OBIBaseModel
import bluepysnap as snap
import os

class Circuit(OBIBaseModel):
    """
    Class representing a circuit, i.e., pointing to a SONATA config.
    """
    name: str
    path: str

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
    def node_sets(self):
        """Returns list of available node sets."""
        return list(self.sonata_circuit.node_sets.content.keys())

    @property
    def node_population_names(self):
        """Returns node population names."""
        return self.sonata_circuit.nodes.population_names

    @property
    def edge_population_names(self):
        """Returns edge population names."""
        return self.sonata_circuit.edges.population_names
