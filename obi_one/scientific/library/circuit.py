import bluepysnap as snap
import numpy as np
from conntility import ConnectivityMatrix

from obi_one.core.base import OBIBaseModel


class Circuit(OBIBaseModel):
    """Class representing a circuit.

    It points to a SONATA config and possible additional assets.
    """

    name: str
    path: str
    matrix_path: str | None = None

    def __init__(self, name: str, path: str, **kwargs) -> None:
        """Initialize object."""
        super().__init__(name=name, path=path, **kwargs)
        c = snap.Circuit(self.path)  # Basic check: Try to load the SONATA circuit w/o error

        if self.matrix_path is not None:
            cmat = ConnectivityMatrix.from_h5(
                self.matrix_path
            )  # Basic check: Try to load the connectivity matrix w/o error
            np.testing.assert_array_equal(
                cmat.vertices["node_ids"], c.nodes[self._default_population_name(c)].ids()
            )  # TODO: This assumes the conn. mat. is the local one; to be extended in the future.

    def __str__(self) -> str:
        """Returns the name as a string representation."""
        return self.name

    @property
    def sonata_circuit(self) -> snap.Circuit:
        """Provide access to SONATA circuit object."""
        return snap.Circuit(self.path)

    @property
    def connectivity_matrix(self) -> ConnectivityMatrix:
        """Provide access to corresponding ConnectivityMatrix object.

        Note: In case of a multi-graph, returns the compressed version.
        """
        if self.matrix_path is None:
            msg = "Connectivity matrix has not been found"
            raise FileNotFoundError(msg)
        cmat = ConnectivityMatrix.from_h5(self.matrix_path)
        if cmat.is_multigraph:
            cmat = cmat.compress()
        return cmat

    @property
    def node_sets(self) -> list:
        """Returns list of available node sets."""
        return list(self.sonata_circuit.node_sets.content.keys())

    @staticmethod
    def get_node_population_names(c: snap.Circuit, *, incl_virtual: bool = True) -> list:
        """Returns node population names."""
        popul_names = c.nodes.population_names
        if not incl_virtual:
            popul_names = [_pop for _pop in popul_names if c.nodes[_pop].type != "virtual"]
        return popul_names

    @staticmethod
    def _default_population_name(c: snap.Circuit) -> str:
        """Returns the default node population name of a SONATA circuit c."""
        popul_names = Circuit.get_node_population_names(c, incl_virtual=False)
        if len(popul_names) == 0:
            return None  # No nodes
        if len(popul_names) != 1:
            msg = "Default node population unknown!"
            raise ValueError(msg)
        return popul_names[0]

    @property
    def default_population_name(self) -> str:
        """Returns the default node population name."""
        return self._default_population_name(self.sonata_circuit)

    @staticmethod
    def get_edge_population_names(c: snap.Circuit, *, incl_virtual: bool = True) -> list:
        """Returns edge population names."""
        popul_names = c.edges.population_names
        if not incl_virtual:
            popul_names = [_pop for _pop in popul_names if c.edges[_pop].source.type != "virtual"]
        return popul_names

    @staticmethod
    def _default_edge_population_name(c: snap.Circuit) -> str:
        """Returns the default edge population name of a SONATA circuit c."""
        popul_names = Circuit.get_edge_population_names(c, incl_virtual=False)
        if len(popul_names) == 0:
            return None  # No edges
        if len(popul_names) != 1:
            msg = "Default edge population unknown!"
            raise ValueError(msg)
        return popul_names[0]

    @property
    def default_edge_population_name(self) -> str:
        """Returns the default edge population name."""
        return self._default_edge_population_name(self.sonata_circuit)
