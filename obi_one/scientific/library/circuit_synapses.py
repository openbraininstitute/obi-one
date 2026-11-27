"""Synapses onto the cells of a circuit, from the indices of its edge files.

Simulations are generated in the API service with the nodes of the circuit only. The SONATA edge
index gives, per node, the ranges of its edges, so the synapses of a node set come from a few MB of
index, read remotely, instead of the edge files.

The layout of an edges file is not trusted. An edge population whose index is missing, too large
to read in the service, or inconsistent with its edges, is counted from its number of edges, which
is HDF5 metadata, and the synapses of a node set are then estimated from the share of the cells it
holds.
"""

import io
import logging
from collections.abc import Callable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from types import MappingProxyType

import h5py
import libsonata
import numpy as np

from obi_one.scientific.library.circuit_constants import (
    TYPES_OF_BIOPHYS_NODES,
    TYPES_OF_CHEMICAL_SYNS,
)

L = logging.getLogger(__name__)

# Bytes of index read at most per edge population: the node and range datasets, 16 bytes a row.
# A population of 1M cells sorted by target takes 32 MB. Above that, the synapses are estimated.
MAX_INDEX_BYTES = 32 * 1024 * 1024

# How many times the mean synapses per cell a node set may hold, for the edge populations that are
# estimated. The cells of one layer or one m-type (contiguous 10% blocks of node ids) hold up to
# 2.2 times the mean in the SSCX circuits of entitycore, and random 1% samples up to 2 times
# (openbraininstitute/prod-circuit-simulation#265).
SUBSET_FACTOR = 2.5

# The synapses per cell of the circuits read so far, which take seconds to read remotely and are
# at most 4 bytes per cell and source population. Kept by the id of the circuit's asset, which
# changes if it is replaced.
MAX_CACHED_CIRCUITS = 16
SYNAPSES_PER_CELL_CACHE: dict[str, dict[str, "CellSynapses"]] = {}
SYNAPSES_PER_CELL_CACHE_LOCK = Lock()


@dataclass(frozen=True, slots=True)
class CellSynapses:
    """The synapses onto the cells of a population of biophysical cells, by source population.

    Kept by source because replay drives the synapses of some sources only, and each replayed
    connection costs memory. Read-only: it is cached and shared by the simulations of a circuit.

    Attributes:
        size: The cells of the population.
        exact: The synapses of each cell from a source, for the edge populations whose index was
            read.
        estimated: The synapses from a source of the edge populations counted in total only.
    """

    size: int
    exact: Mapping[str, np.ndarray] = field(default_factory=dict)
    estimated: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Make the mappings and the per-cell arrays read-only too."""
        for counts in self.exact.values():
            counts.flags.writeable = False
        object.__setattr__(self, "exact", MappingProxyType(dict(self.exact)))
        object.__setattr__(self, "estimated", MappingProxyType(dict(self.estimated)))


def synapses_by_source(cells: CellSynapses, ids: list[int] | np.ndarray) -> dict[str, float]:
    """The synapses onto the cells ``ids`` of a population from each source, estimated in part.

    The synapses of a source counted in total give the cells their share of them, times
    ``SUBSET_FACTOR``, up to the total.
    """
    ids = np.unique(np.asarray(ids, dtype=np.int64))
    ids = ids[(ids >= 0) & (ids < cells.size)]
    counts = {source: float(c[ids].sum(dtype=np.int64)) for source, c in cells.exact.items()}
    share = min(1.0, SUBSET_FACTOR * len(ids) / cells.size) if cells.size else 0.0
    for source, synapses in cells.estimated.items():
        counts[source] = counts.get(source, 0.0) + synapses * share
    return counts


def _exact_synapses_per_cell(group: h5py.Group, size: int, n_edges: int) -> np.ndarray | None:
    """The edges onto each node from the ``target_to_source`` index, or None if it is not usable.

    ``node_id_to_ranges`` gives each node the ranges ``[first, last)`` of ``range_to_edge_id``, and
    each of those the edges ``[start, end)``. The index is used only if it is small enough and if
    it accounts for every edge: some writers give it fewer or more rows than the population.
    """
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

    The chemical edge populations onto a population are added up. Only the edge indices and the
    shapes of the edge datasets are read, and each edges file is opened once, whatever the number
    of populations in it. An edge population that cannot be read exactly is counted in total.

    Args:
        circuit_config_path: The circuit, whose nodes are on disk and edge files need not be.
        open_edges_file: Opens an edges file, given its path in the circuit config, for example
            as a remote file. By default the path itself is opened.

    Returns:
        The synapses of the cells, by population of cells. An edges file that cannot be opened
        or read raises, since a count without it would be too low.
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
        target: CellSynapses(size, exact[target], estimated[target])
        for target, size in sizes.items()
    }


def cached_synapses_per_cell(
    circuit_key: str, read: Callable[[], dict[str, CellSynapses]]
) -> dict[str, CellSynapses]:
    """The synapses per cell of a circuit, read with ``read`` the first time only."""
    with SYNAPSES_PER_CELL_CACHE_LOCK:
        if circuit_key in SYNAPSES_PER_CELL_CACHE:
            # The least recently used circuit is dropped first.
            SYNAPSES_PER_CELL_CACHE[circuit_key] = SYNAPSES_PER_CELL_CACHE.pop(circuit_key)
            return SYNAPSES_PER_CELL_CACHE[circuit_key]
    synapses = read()
    with SYNAPSES_PER_CELL_CACHE_LOCK:
        if len(SYNAPSES_PER_CELL_CACHE) >= MAX_CACHED_CIRCUITS:
            del SYNAPSES_PER_CELL_CACHE[next(iter(SYNAPSES_PER_CELL_CACHE))]
        SYNAPSES_PER_CELL_CACHE[circuit_key] = synapses
    return synapses


def count_synapses_by_source(
    synapses: dict[str, CellSynapses], node_ids: dict[str, list[int]]
) -> dict[str, float]:
    """The synapses onto the given cells, by population, from each source population."""
    counts: dict[str, float] = {}
    for pop, ids in node_ids.items():
        if pop in synapses:
            for source, n in synapses_by_source(synapses[pop], ids).items():
                counts[source] = counts.get(source, 0.0) + n
    return counts


def count_synapses(synapses: dict[str, CellSynapses], node_ids: dict[str, list[int]]) -> int:
    """The synapses onto the given cells, by population, from ``read_synapses_per_cell``."""
    return round(sum(count_synapses_by_source(synapses, node_ids).values()))
