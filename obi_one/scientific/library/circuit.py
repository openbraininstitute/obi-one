import json
import logging
from pathlib import Path
from typing import Any, Literal

import bluepysnap as snap
import libsonata
import morphio
import numpy as np
from conntility import ConnectivityMatrix

from obi_one.core.base import OBIBaseModel
from obi_one.scientific.library.circuit_metrics import (
    TYPES_OF_BIOPHYS_NODES,
    TYPES_OF_POINT_NODES,
    TYPES_OF_VIRTUAL_NODES,
)
from obi_one.scientific.library.morphology_loader import (
    load_morphology_nrn_order,
    load_morphology_nrn_order_from_collection,
)

L = logging.getLogger(__name__)

CIRCUIT_MOD_DIR = "mod"

# SONATA `alternate_morphologies` keys, mapped to their file extension. Order matters: it is
# also the format-resolution priority used by app.services.circuit_visualization.resolve_morph_path.
ALTERNATE_MORPHOLOGY_FORMATS: dict[str, Literal["asc", "h5"]] = {
    "neurolucida-asc": "asc",
    "h5v1": "h5",
}


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
        """Circuit directory."""
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
        """List of available node sets."""
        return list(self.sonata_circuit.node_sets.content)

    @staticmethod
    def get_node_population_names(
        c: snap.Circuit,
        *,
        incl_virtual: bool = True,
        incl_point: bool = True,
        incl_biophysical: bool = True,
    ) -> list:
        """Returns node population names."""
        popul_names = c.nodes.population_names
        if not incl_virtual:
            popul_names = [
                pop for pop in popul_names if c.nodes[pop].type not in TYPES_OF_VIRTUAL_NODES
            ]
        if not incl_point:
            popul_names = [
                pop for pop in popul_names if c.nodes[pop].type not in TYPES_OF_POINT_NODES
            ]
        if not incl_biophysical:
            popul_names = [
                pop for pop in popul_names if c.nodes[pop].type not in TYPES_OF_BIOPHYS_NODES
            ]
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
        """The default node population name."""
        return self._default_population_name(self.sonata_circuit)

    @staticmethod
    def get_edge_population_names(
        c: snap.Circuit,
        *,
        incl_virtual: bool = True,
        incl_point: bool = True,
        incl_biophysical: bool = True,
    ) -> list:
        """Returns edge population names."""
        popul_names = c.edges.population_names
        if not incl_virtual:
            popul_names = [
                pop for pop in popul_names if c.edges[pop].source.type not in TYPES_OF_VIRTUAL_NODES
            ]
        if not incl_point:
            popul_names = [
                pop
                for pop in popul_names
                if c.edges[pop].source.type not in TYPES_OF_POINT_NODES
                and c.edges[pop].target.type not in TYPES_OF_POINT_NODES
            ]
        if not incl_biophysical:
            popul_names = [
                pop
                for pop in popul_names
                if c.edges[pop].source.type not in TYPES_OF_BIOPHYS_NODES
                and c.edges[pop].target.type not in TYPES_OF_BIOPHYS_NODES
            ]
        return popul_names

    @staticmethod
    def _default_edge_population_name(c: snap.Circuit) -> str | None:
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
            return None
        if len(intrinsic_epops) > 1:
            # Try to infer from population name
            intrinsic_epops = [
                pop for pop in intrinsic_epops if pop.startswith(f"{default_npop}__{default_npop}")
            ]
        if len(intrinsic_epops) == 1:
            return intrinsic_epops[0]
        msg = "Default edge population unknown!"
        raise ValueError(msg)

    @property
    def default_edge_population_name(self) -> str | None:
        """The default edge population name."""
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
        except Exception:  # ruff: ignore[blind-except]
            try:
                return node["morphology"]
            except Exception as e:
                msg = (
                    f"Could not find morphology attribute for node_id={node_id} "
                    f"in population '{pop}'."
                )
                raise KeyError(msg) from e

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

        candidates = [morph_dir / morph_name]
        morph_name_path = Path(morph_name)
        if morph_name_path.is_absolute() or len(morph_name_path.parts) > 1:
            candidates.append(self._resolve_circuit_path(morph_name))

        for candidate in candidates:
            if candidate.exists():
                return candidate

            for ext in (".asc", ".swc", ".h5"):
                path = Path(f"{candidate}{ext}")
                if path.exists():
                    return path

        msg = (
            f"Could not find morphology file for node_id={node_id}, population={population!r}. "
            f"Tried {candidates} and common extensions."
        )
        raise FileNotFoundError(msg)

    def _alternate_morphology_base(self, population: str | None, key: str) -> Path | None:
        """The resolved `alternate_morphologies` base for one SONATA key, if the circuit has it.

        The base may be a directory or an `.h5` container.
        """
        alternates = self._population_config(population).get("alternate_morphologies") or {}
        raw_path = alternates.get(key)
        return self._resolve_circuit_path(raw_path) if raw_path else None

    def load_morphology(self, node_id: int, population: str | None = None) -> morphio.Morphology:
        """Load a node's morphology, preferring h5, then swc, then asc.

        A simulation reads the h5 morphology when the circuit carries one - it is the format the
        pipeline treats as canonical - and only falls back to the swc under `morphologies_dir` or
        the asc alternate when it does not. The alternates also cover containerized circuits,
        which hold every morphology in a single `.h5` container with no per-node file for
        `get_morphology_path` to resolve.
        """
        morph_name = self.get_morphology_name(node_id, population=population)
        attempted: list[str] = []

        def _from_container(key: str) -> morphio.Morphology | None:
            base = self._alternate_morphology_base(population, key)
            if base is None:
                return None
            extension = f".{ALTERNATE_MORPHOLOGY_FORMATS[key]}"
            attempted.append(f"{base} ({extension})")
            try:
                return load_morphology_nrn_order_from_collection(base, morph_name, extension)
            except (morphio.MorphioError, OSError, RuntimeError) as exc:
                L.debug("Could not load '%s' from %s: %s", morph_name, base, exc)
                return None

        def _from_morphologies_dir() -> morphio.Morphology | None:
            try:
                path = self.get_morphology_path(node_id, population=population)
            except (FileNotFoundError, KeyError):
                return None
            attempted.append(str(path))
            try:
                return load_morphology_nrn_order(path)
            except (morphio.MorphioError, OSError, RuntimeError) as exc:
                L.debug("Could not load '%s' from %s: %s", morph_name, path, exc)
                return None

        # h5 (canonical for simulation), then the swc under morphologies_dir, then the asc.
        for attempt in (
            lambda: _from_container("h5v1"),
            _from_morphologies_dir,
            lambda: _from_container("neurolucida-asc"),
        ):
            morphology = attempt()
            if morphology is not None:
                return morphology

        msg = (
            f"Could not load morphology '{morph_name}' for node_id={node_id}, "
            f"population={population!r}. No file was found under 'morphologies_dir' and "
            f"'alternate_morphologies' did not provide it either (tried: {attempted or 'none'})."
        )
        raise FileNotFoundError(msg)

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


def ensure_mechanisms_dir(circuit_config_path: Path, edge_population_name: str) -> Path:
    """The mechanisms directory for one edge population, declaring it if not already set.

    Reads it through libsonata (`edge_population_properties(...).mechanisms_dir`) rather than
    the raw config, so this sees exactly what the simulator would: a value set directly on
    `edge_population_name`, falling back to `components.mechanisms_dir`, with manifest
    variables (e.g. `$BASE_DIR`) already substituted and the path already absolute -
    libsonata resolves both of those, and a hand-rolled reimplementation of either would risk
    disagreeing with it (and does; the population-level override was missed by an earlier
    version of this function).

    Some circuits keep their compiled mechanisms in `CIRCUIT_MOD_DIR` without naming it anywhere
    in the config - libsonata reports that as `""`, not as this repo's fallback folder, so a `""`
    is treated the same as an explicit absence: falls back to that folder rather than being
    treated as "no mechanisms directory", and the fallback is written into `components` (never
    into the population, which the config may not name explicitly at all), so the output circuit
    states explicitly where its mechanisms live rather than relying on the same unstated
    convention. Directory created if it does not exist yet, since a fresh copy of a circuit that
    relied on the convention may not have had one either.
    """
    circuit = libsonata.CircuitConfig.from_file(str(circuit_config_path))
    mechanisms_dir_raw = circuit.edge_population_properties(edge_population_name).mechanisms_dir

    if mechanisms_dir_raw:
        mechanisms_dir = Path(mechanisms_dir_raw)
    else:
        with circuit_config_path.open(encoding="utf-8") as f:
            cfg_dict = json.load(f)
        cfg_dict.setdefault("components", {})["mechanisms_dir"] = f"$BASE_DIR/{CIRCUIT_MOD_DIR}"
        with circuit_config_path.open("w", encoding="utf-8") as f:
            json.dump(cfg_dict, f, indent=2)
        mechanisms_dir = circuit_config_path.parent / CIRCUIT_MOD_DIR

    mechanisms_dir.mkdir(parents=True, exist_ok=True)
    return mechanisms_dir
