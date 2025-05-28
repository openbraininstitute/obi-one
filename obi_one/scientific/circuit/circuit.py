import bluepysnap as snap
from conntility import ConnectivityMatrix

from obi_one.core.base import OBIBaseModel


class Circuit(OBIBaseModel):
    """Class representing a circuit, i.e., pointing to a SONATA config and possible additional assets."""

    name: str
    path: str
    matrix_path: str = None

    def __init__(self, name, path, **kwargs):
        super().__init__(name=name, path=path, **kwargs)
        _c = snap.Circuit(self.path)  # Basic check: Try to load the SONATA circuit w/o error

    def __str__(self):
        return self.name

    @property
    def sonata_circuit(self):
        """Provide access to SONATA circuit object."""
        return snap.Circuit(self.path)
    
    @property
    def connectivity_matrix(self):
        """Provide access to corresponding ConnectivityMatrix object."""
        if self.matrix_path is None:
            raise ValueError("Connectivity matrix has not been found")
        return ConnectivityMatrix.from_h5(self.matrix_path)

    @property
    def node_sets(self):
        """Returns list of available node sets."""
        return list(self.sonata_circuit.node_sets.content.keys())

    def get_node_population_names(self, incl_virtual=True):
        """Returns node population names."""
        popul_names = self.sonata_circuit.nodes.population_names
        if not incl_virtual:
            popul_names = [
                _pop for _pop in popul_names if self.sonata_circuit.nodes[_pop].type != "virtual"
            ]
        return popul_names

    @property
    def default_population_name(self):
        """Returns the default node population name."""
        popul_names = self.get_node_population_names(incl_virtual=False)
        assert len(popul_names) == 1, "Default node population unknown!"
        return popul_names[0]

    def get_edge_population_names(self, incl_virtual=True):
        """Returns edge population names."""
        popul_names = self.sonata_circuit.edges.population_names
        if not incl_virtual:
            popul_names = [
                _pop
                for _pop in popul_names
                if self.sonata_circuit.edges[_pop].source.type != "virtual"
            ]
        return popul_names
