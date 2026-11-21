"""Synapses onto the cells of a circuit, from the indices of its edge files.

Simulations are generated in the API service with the nodes of the circuit only. The SONATA edge
index gives, per node, the ranges of its edges, so the synapses of a node set come from a few MB of
index, read remotely, instead of the edge files.
"""

import io
from collections import defaultdict
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from threading import Lock

import h5py
import libsonata
import numpy as np

from obi_one.scientific.library.circuit_constants import (
    TYPES_OF_BIOPHYS_NODES,
    TYPES_OF_CHEMICAL_SYNS,
)

# Ranges read at most per index, 16 bytes each. Above that the edges of each node are estimated.
MAX_RANGES_READ = 1_000_000

# The synapses per cell of the circuits read so far, which take seconds to read remotely and are
# a few bytes per cell. Kept by the id of the circuit's asset, which changes if it is replaced.
MAX_CACHED_CIRCUITS = 16
SYNAPSES_PER_CELL_CACHE: dict[str, dict[str, np.ndarray]] = {}
SYNAPSES_PER_CELL_CACHE_LOCK = Lock()


def _synapses_per_cell(group: h5py.Group) -> np.ndarray:
    """The edges onto each node of an edge population, from its ``target_to_source`` index.

    ``node_id_to_ranges`` gives each node the ranges ``[first, last)`` of ``range_to_edge_id``, and
    each of those the edges ``[start, end)``. A file sorted by target has one range per node, so
    reading ``range_to_edge_id`` is cheap and the count is exact. Otherwise only the number of
    ranges of each node is read, times the mean edges per range.
    """
    index = group["indices/target_to_source"]
    node_ranges = index["node_id_to_ranges"][:].astype(np.int64)
    ranges = index["range_to_edge_id"]
    if ranges.shape[0] <= MAX_RANGES_READ:
        edges_per_range = np.diff(ranges[:].astype(np.int64), axis=1).ravel()
        cumulative = np.concatenate([[0], np.cumsum(edges_per_range)])
        return (cumulative[node_ranges[:, 1]] - cumulative[node_ranges[:, 0]]).astype(np.float64)
    mean_edges_per_range = group["source_node_id"].shape[0] / ranges.shape[0]
    return np.diff(node_ranges, axis=1).ravel() * mean_edges_per_range


def read_synapses_per_cell(
    circuit_config_path: str | Path,
    open_edges_file: Callable[[str], io.IOBase] | None = None,
) -> dict[str, np.ndarray]:
    """The synapses onto each cell, for each population of biophysical cells.

    The chemical edge populations onto a population are added up. Only the edge indices are read,
    and each edges file is opened once, whatever the number of populations in it.

    Args:
        circuit_config_path: The circuit, whose edge files need not be on disk.
        open_edges_file: Opens an edges file, given its path in the circuit config, for example
            as a remote file. By default the path itself is opened.

    Returns:
        An array of the synapses of each cell, by population of cells.
    """
    config = libsonata.CircuitConfig.from_file(str(circuit_config_path))
    node_types = {
        name: config.node_population_properties(name).type for name in config.node_populations
    }
    populations_by_file = defaultdict(list)
    for name in config.edge_populations:
        properties = config.edge_population_properties(name)
        if properties.type in TYPES_OF_CHEMICAL_SYNS:
            populations_by_file[properties.elements_path].append(name)

    synapses = {}
    for path, names in populations_by_file.items():
        opened = open_edges_file(path) if open_edges_file else nullcontext(path)
        with opened as edges_file, h5py.File(edges_file, "r") as f:
            for name in names:
                group = f["edges"][name]
                target = group["target_node_id"].attrs["node_population"]
                if node_types[target] in TYPES_OF_BIOPHYS_NODES:
                    synapses[target] = synapses.get(target, 0) + _synapses_per_cell(group)
    return synapses


def cached_synapses_per_cell(
    circuit_key: str, read: Callable[[], dict[str, np.ndarray]]
) -> dict[str, np.ndarray]:
    """The synapses per cell of a circuit, read with ``read`` the first time only."""
    with SYNAPSES_PER_CELL_CACHE_LOCK:
        if circuit_key in SYNAPSES_PER_CELL_CACHE:
            return SYNAPSES_PER_CELL_CACHE[circuit_key]
    synapses = read()
    with SYNAPSES_PER_CELL_CACHE_LOCK:
        if len(SYNAPSES_PER_CELL_CACHE) >= MAX_CACHED_CIRCUITS:
            del SYNAPSES_PER_CELL_CACHE[next(iter(SYNAPSES_PER_CELL_CACHE))]
        SYNAPSES_PER_CELL_CACHE[circuit_key] = synapses
    return synapses


def count_synapses(synapses: dict[str, np.ndarray], node_ids: dict[str, list[int]]) -> int:
    """The synapses onto the given cells, by population, from ``read_synapses_per_cell``."""
    return round(sum(synapses[pop][ids].sum() for pop, ids in node_ids.items() if pop in synapses))
