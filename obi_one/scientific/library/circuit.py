from pathlib import Path
from typing import Any

import bluepysnap as snap
import morphio
import numpy as np
from conntility import ConnectivityMatrix

from obi_one.core.base import OBIBaseModel
from obi_one.scientific.library.morphology_loader import load_morphology_nrn_order

CIRCUIT_MOD_DIR = "mod"


class Circuit(OBIBaseModel):
    """Class representing a circuit.

    It points to a SONATA config and possible additional assets.
    """

    name: str
    path: str
    matrix_path: str | None = None

    def __init__(self, name: str, path: str, **kwargs) -> None:
        """Initialize object."""
        super().__init__(name=name, path=path, **kwargs)  # ty:ignore[unknown-argument]
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
    def directory(self) -> Path:
        """Return circuit directory."""
        return Path(self.path).parent

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
    def get_node_population_names(
        c: snap.Circuit, *, incl_virtual: bool = True, incl_point: bool = True
    ) -> list:
        """Returns node population names."""
        popul_names = c.nodes.population_names
        if not incl_virtual:
            popul_names = [pop for pop in popul_names if c.nodes[pop].type != "virtual"]
        if not incl_point:
            # Exclude "point_neuron", "point_process", etc. types
            popul_names = [pop for pop in popul_names if "point_" not in c.nodes[pop].type]
        return popul_names

    @staticmethod
    def _default_population_name(c: snap.Circuit) -> str:
        """Returns the default node population name of a SONATA circuit c."""
        popul_names = Circuit.get_node_population_names(c, incl_virtual=False, incl_point=False)
        if len(popul_names) == 0:
            # Include point neurons
            popul_names = Circuit.get_node_population_names(c, incl_virtual=False, incl_point=True)
        if len(popul_names) == 0:
            return None  # No biophysical/point neurons  # ty:ignore[invalid-return-type]
        if len(popul_names) != 1:
            msg = "Default node population unknown!"
            raise ValueError(msg)
        return popul_names[0]

    @property
    def default_population_name(self) -> str:
        """Returns the default node population name."""
        return self._default_population_name(self.sonata_circuit)

    @staticmethod
    def get_edge_population_names(
        c: snap.Circuit, *, incl_virtual: bool = True, incl_point: bool = True
    ) -> list:
        """Returns edge population names."""
        popul_names = c.edges.population_names
        if not incl_virtual:
            popul_names = [pop for pop in popul_names if c.edges[pop].source.type != "virtual"]
        if not incl_point:
            # Exclude "point_neuron", "point_process", etc. source/target types
            popul_names = [
                pop
                for pop in popul_names
                if "point_" not in c.edges[pop].source.type
                and "point_" not in c.edges[pop].target.type
            ]
        return popul_names

    @staticmethod
    def _default_edge_population_name(c: snap.Circuit) -> str:
        """Returns the default edge population name of a SONATA circuit c."""
        try:
            default_npop = Circuit._default_population_name(c)
        except ValueError as e:
            msg = f"Cannot determine default edge population: {e}"
            raise ValueError(msg) from e
        if default_npop is None:
            return None
        epop_names = Circuit.get_edge_population_names(c, incl_virtual=False, incl_point=True)
        intrinsic_epops = [
            epop
            for epop in epop_names
            if c.edges[epop].source.name == default_npop
            and c.edges[epop].target.name == default_npop
        ]
        if len(intrinsic_epops) == 0:
            return None  # ty:ignore[invalid-return-type]
        if len(intrinsic_epops) > 1:
            msg = "Default edge population unknown!"
            raise ValueError(msg)
        return intrinsic_epops[0]

    @property
    def default_edge_population_name(self) -> str:
        """Returns the default edge population name."""
        return self._default_edge_population_name(self.sonata_circuit)

    def get_cell(self, node_id: int, population: str | None = None) -> Any:
        """Return BluePySnap node accessor for one cell."""
        c = self.sonata_circuit
        pop = population or self.default_population_name
        return c.nodes[pop].get(node_id)

    def get_morphology_name(self, node_id: int, population: str | None = None) -> str:
        pop = population or self.default_population_name
        node = self.sonata_circuit.nodes[pop].get(node_id)
        try:
            return node.morphology
        except Exception:  # noqa: BLE001
            try:
                return node["morphology"]
            except Exception as e:
                msg = (
                    f"Could not find morphology attribute for node_id={node_id} "
                    f"in population '{pop}'."
                )
                raise KeyError(msg) from e

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

        msg = f"Could not find population config for population={pop!r} in SONATA circuit."
        raise KeyError(msg)

    def _population_config(self, population: str | None) -> dict[str, Any]:
        c = self.sonata_circuit
        pop = population or self.default_population_name

        components = c.config.get("components", {})
        networks = c.config.get("networks", {})

        for nodes_entry in networks.get("nodes", []):
            pops = nodes_entry.get("populations", {})
            if pop in pops:
                return {
                    **components,
                    **pops[pop],
                }

        msg = f"Could not find population config for population={pop!r} in SONATA circuit."
        raise KeyError(msg)

    def _resolve_circuit_path(self, raw_path: str | Path) -> Path:
        path = str(raw_path)

        manifest = self.sonata_circuit.config.get("manifest", {})
        manifest = {".": "."} | manifest

        for key, value in sorted(manifest.items(), key=lambda item: len(item[0]), reverse=True):
            if path.startswith(key):
                path = path.replace(key, value, 1)
                break

        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = self.directory / resolved

        return resolved

    def get_morphology_path(self, node_id: int, population: str | None = None) -> Path:
        morph_name = self.get_morphology_name(node_id, population=population)
        pop_cfg = self._population_config(population)

        morph_dir_raw = pop_cfg.get("morphologies_dir")
        if not morph_dir_raw:
            msg = f"No 'morphologies_dir' found in config for population={population!r}."
            raise KeyError(msg)

        morph_dir = self._resolve_circuit_path(morph_dir_raw)

        direct = morph_dir / morph_name
        if direct.exists():
            return direct

        for ext in (".asc", ".swc", ".h5"):
            path = morph_dir / f"{morph_name}{ext}"
            if path.exists():
                return path

        msg = (
            f"Could not find morphology file for node_id={node_id}, population={population!r}. "
            f"Tried '{direct}' and common extensions in '{morph_dir}'."
        )
        raise FileNotFoundError(msg)

    def load_morphology(self, node_id: int, population: str | None = None) -> morphio.Morphology:
        return load_morphology_nrn_order(self.get_morphology_path(node_id, population=population))

    @property
    def mechanisms_dir(self) -> Path:
        # TODO: There should be only ONE convention for output dir of mechs
        if type(self).__name__ == "Circuit":
            path = self.directory / CIRCUIT_MOD_DIR
        else:
            path = self.directory / "mechanisms"

        if not path.exists():
            msg = f"{path} does not exist."
            raise FileNotFoundError(msg)
        if not path.is_dir():
            msg = f"{path} is not a mechanisms directory."
            raise NotADirectoryError(msg)
        return path
