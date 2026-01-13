from pathlib import Path
import bluepysnap as snap
import morphio
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


    def get_cell(self, node_id: int, population: str | None = None):
        """Return BluePySnap node accessor for one cell."""
        c = self.sonata_circuit
        pop = population or self.default_population_name
        return c.nodes[pop].get(node_id)

    def get_morphology_name(self, node_id: int, population: str | None = None) -> str:
        pop = population or self.default_population_name
        node = self.sonata_circuit.nodes[pop].get(node_id)
        # common patterns in BluePySnap:
        # - node.morphology
        # - node["morphology"]
        try:
            return node.morphology
        except Exception:
            try:
                return node["morphology"]
            except Exception as e:
                raise KeyError(
                    f"Could not read morphology attribute for node_id={node_id} in population '{pop}'."
                ) from e

    def _population_config(self, population: str | None) -> dict:
        c = self.sonata_circuit
        pop = population or self.default_population_name

        networks = c.config.get("networks", {})
        for nodes_entry in networks.get("nodes", []):
            pops = nodes_entry.get("populations", {})
            if pop in pops:
                return pops[pop]

        # Fallback: some configs expose components at top-level
        components = c.config.get("components")
        if components is not None:
            return {"morphologies_dir": components.get("morphologies_dir")}

        raise KeyError(f"Could not find population config for population={pop!r}")

    def get_morphology_path(self, node_id: int, population: str | None = None) -> Path:
        morph_name = self.get_morphology_name(node_id, population=population)
        pop_cfg = self._population_config(population)
        morph_dir_raw = pop_cfg.get("morphologies_dir")
        if not morph_dir_raw:
            raise KeyError("No 'morphologies_dir' found in population config.")

        morph_dir = Path(morph_dir_raw)

        # If morph_name already contains an extension, try directly first.
        direct = morph_dir / morph_name
        if direct.exists():
            return direct

        # Try common extensions if the stored name is extension-less.
        for ext in (".asc", ".swc", ".h5"):
            p = morph_dir / f"{morph_name}{ext}"
            if p.exists():
                return p

        raise FileNotFoundError(
            f"Could not find morphology file for node_id={node_id}, population={population}. "
            f"Tried '{direct}' and common extensions in '{morph_dir}'."
        )

    def load_morphology(self, node_id: int, population: str | None = None) -> morphio.Morphology:
        return morphio.Morphology(str(self.get_morphology_path(node_id, population=population)))