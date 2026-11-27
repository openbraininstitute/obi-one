"""Synapses onto the cells of a circuit, from the indices of its edge files.

See docs/circuit-simulation-resources.md.
"""

import io
import logging
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path

import h5py
import libsonata
import numpy as np
from pydantic import BaseModel, ConfigDict

from obi_one.scientific.library.circuit_constants import (
    TYPES_OF_BIOPHYS_NODES,
    TYPES_OF_CHEMICAL_SYNS,
)

L = logging.getLogger(__name__)

MAX_INDEX_BYTES = 32 * 1024 * 1024
SUBSET_FACTOR = 2.5

# Kept next to the staged circuit config, which the simulations of a campaign share.
SYNAPSES_FILE_NAME = "synapses_per_cell.npz"


class CellSynapses(BaseModel):
    """The synapses onto the cells of a population, by source population.

    Attributes:
        size: The cells of the population.
        exact: The synapses of each cell, from the edge populations whose index was read.
        estimated: The synapses of the edge populations counted in total only.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    size: int
    exact: dict[str, np.ndarray] = {}
    estimated: dict[str, int] = {}

    def count_by_source(self, ids: list[int] | np.ndarray) -> dict[str, float]:
        """The synapses onto the cells ``ids`` from each source."""
        ids = np.unique(np.asarray(ids, dtype=np.int64))
        ids = ids[(ids >= 0) & (ids < self.size)]
        counts = {source: float(c[ids].sum(dtype=np.int64)) for source, c in self.exact.items()}
        share = min(1.0, SUBSET_FACTOR * len(ids) / self.size) if self.size else 0.0
        for source, synapses in self.estimated.items():
            counts[source] = counts.get(source, 0.0) + synapses * share
        return counts

    def count(self, ids: list[int] | np.ndarray) -> float:
        """The synapses onto the cells ``ids``."""
        return sum(self.count_by_source(ids).values())


def _exact_synapses_per_cell(group: h5py.Group, size: int, n_edges: int) -> np.ndarray | None:
    """The edges onto each node from the ``target_to_source`` index, or None if not usable."""
    if "indices/target_to_source" not in group:
        return None
    index = group["indices/target_to_source"]
    if "node_id_to_ranges" not in index or "range_to_edge_id" not in index:
        return None
    node_ranges_ds, ranges_ds = index["node_id_to_ranges"], index["range_to_edge_id"]
    if (min(node_ranges_ds.shape[0], size) + ranges_ds.shape[0]) * 16 > MAX_INDEX_BYTES:
        return None
    first, last = node_ranges_ds[:size].astype(np.int64).reshape(-1, 2).T
    ranges = ranges_ds[:].astype(np.int64).reshape(-1, 2)
    edges_per_range = np.diff(ranges, axis=1).ravel()
    if (
        np.any(edges_per_range < 0)
        or np.any(last < first)
        or first.min(initial=0) < 0
        or last.max(initial=0) > len(ranges)
    ):
        return None
    cumulative = np.concatenate([[0], np.cumsum(edges_per_range)])
    counts = cumulative[last] - cumulative[first]
    counts = np.pad(counts, (0, size - len(counts)))
    if counts.sum() != n_edges:
        return None
    return counts


def _attribute(dataset: h5py.Dataset, name: str) -> str:
    value = dataset.attrs[name]
    return value.decode() if isinstance(value, bytes) else str(value)


def read_synapses_per_cell(
    circuit_config_path: str | Path,
    open_edges_file: Callable[[str], io.IOBase] | None = None,
) -> dict[str, CellSynapses]:
    """The synapses onto each cell, for each population of biophysical cells.

    Args:
        circuit_config_path: The circuit, whose nodes are on disk.
        open_edges_file: Opens an edges file given its path in the config. By default, the path.

    Returns:
        The synapses by population of cells. An edges file that cannot be read raises.
    """
    config = libsonata.CircuitConfig.from_file(str(circuit_config_path))
    sizes = {
        name: size
        for name in config.node_populations
        if config.node_population_properties(name).type in TYPES_OF_BIOPHYS_NODES
        and (size := config.node_population(name).size)
    }
    populations_by_file: dict[str, list[str]] = {}
    for name in config.edge_populations:
        properties = config.edge_population_properties(name)
        if properties.type in TYPES_OF_CHEMICAL_SYNS:
            populations_by_file.setdefault(properties.elements_path, []).append(name)

    exact: dict[str, dict[str, np.ndarray]] = {target: {} for target in sizes}
    estimated: dict[str, dict[str, int]] = {target: {} for target in sizes}
    for path, names in populations_by_file.items():
        opened = open_edges_file(path) if open_edges_file else nullcontext(path)
        with opened as edges_file, h5py.File(edges_file, "r") as f:
            for name in names:
                try:
                    group = f["edges"][name]
                    target = _attribute(group["target_node_id"], "node_population")
                    source = _attribute(group["source_node_id"], "node_population")
                    n_edges = group["source_node_id"].shape[0]
                except (KeyError, OSError, ValueError) as e:
                    L.warning("Edge population %s of %s is not counted: %s", name, path, e)
                    continue
                if target not in sizes:
                    continue
                counts = _exact_synapses_per_cell(group, sizes[target], n_edges)
                if counts is None:
                    L.info("Edge population %s: %d synapses, not counted per cell", name, n_edges)
                    estimated[target][source] = estimated[target].get(source, 0) + n_edges
                else:
                    total = exact[target].get(source, 0)
                    exact[target][source] = (total + counts).astype(np.uint32)
    return {
        target: CellSynapses(size=size, exact=exact[target], estimated=estimated[target])
        for target, size in sizes.items()
    }


def save_synapses_per_cell(path: Path, synapses: dict[str, CellSynapses]) -> None:
    """Write the result of ``read_synapses_per_cell`` to an ``.npz`` file."""
    arrays = {}
    for target, cells in synapses.items():
        arrays[f"size/{target}"] = np.array(cells.size)
        for source, counts in cells.exact.items():
            arrays[f"exact/{target}/{source}"] = counts
        for source, total in cells.estimated.items():
            arrays[f"estimated/{target}/{source}"] = np.array(total)
    np.savez(path, allow_pickle=False, **arrays)


def load_synapses_per_cell(path: Path) -> dict[str, CellSynapses]:
    """Read a file written by ``save_synapses_per_cell``."""
    with np.load(path) as f:
        parts = [(tuple(key.split("/")), f[key]) for key in f.files]
    return {
        key[1]: CellSynapses(
            size=int(value),
            exact={k[2]: v for k, v in parts if k[:2] == ("exact", key[1])},
            estimated={k[2]: int(v) for k, v in parts if k[:2] == ("estimated", key[1])},
        )
        for key, value in parts
        if key[0] == "size"
    }


def staged_synapses_per_cell(
    circuit_config_path: Path, read: Callable[[], dict[str, CellSynapses]]
) -> dict[str, CellSynapses]:
    """The synapses per cell of a staged circuit, read with ``read`` once and kept beside it."""
    path = circuit_config_path.parent / SYNAPSES_FILE_NAME
    if path.exists():
        return load_synapses_per_cell(path)
    synapses = read()
    save_synapses_per_cell(path, synapses)
    return synapses


def count_synapses_by_source(
    synapses: dict[str, CellSynapses], node_ids: dict[str, list[int]]
) -> dict[str, float]:
    """The synapses onto the given cells, by population, from each source population."""
    counts: dict[str, float] = {}
    for pop, ids in node_ids.items():
        if pop in synapses:
            for source, n in synapses[pop].count_by_source(ids).items():
                counts[source] = counts.get(source, 0.0) + n
    return counts


def count_synapses(synapses: dict[str, CellSynapses], node_ids: dict[str, list[int]]) -> int:
    """The synapses onto the given cells, by population, from ``read_synapses_per_cell``."""
    return round(sum(count_synapses_by_source(synapses, node_ids).values()))
