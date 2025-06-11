from typing import Optional
import bluepysnap as snap
from conntility import ConnectivityMatrix
import numpy as np

from obi_one.core.base import OBIBaseModel


class Circuit(OBIBaseModel):
    """Class representing a circuit, i.e., pointing to a SONATA config and possible additional assets."""

    name: str
    path: str
    matrix_path: Optional[str] = None

    def __init__(self, name, path, **kwargs):
        super().__init__(name=name, path=path, **kwargs)
        _c = snap.Circuit(self.path)  # Basic check: Try to load the SONATA circuit w/o error

        if self.matrix_path is not None:
            _cmat = ConnectivityMatrix.from_h5(self.matrix_path)  # Basic check: Try to load the connectivity matrix w/o error
            np.testing.assert_array_equal(_cmat.vertices["node_ids"], _c.nodes[self._default_population_name(_c)].ids()) # TODO: This assumes the connectivity matrix is the local one, might nee to be extended in the future.

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
            raise FileNotFoundError("Connectivity matrix has not been found")
        return ConnectivityMatrix.from_h5(self.matrix_path)

    @property
    def node_sets(self):
        """Returns list of available node sets."""
        return list(self.sonata_circuit.node_sets.content.keys())

    @staticmethod
    def get_node_population_names(c: snap.Circuit,incl_virtual=True):
        """Returns node population names."""
        popul_names = c.nodes.population_names
        if not incl_virtual:
            popul_names = [
                _pop for _pop in popul_names if c.nodes[_pop].type != "virtual"
            ]
        return popul_names
    
    @staticmethod
    def _default_population_name(c: snap.Circuit):
        """Returns the default node population name of a SONATA circuit c."""
        popul_names = Circuit.get_node_population_names(c, incl_virtual=False)
        assert len(popul_names) == 1, "Default node population unknown!"
        return popul_names[0]

    @property
    def default_population_name(self):
        """Returns the default node population name."""
        return self._default_population_name(self.sonata_circuit)

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
