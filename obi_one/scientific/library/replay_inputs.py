"""The sources and spikes of the spike replay inputs of a simulation.

Replay costs neurodamus memory twice: each connection from a replayed source holds its own spike
train, and every MPI rank reads every spike file whole while it sets the replay up. Generation
writes the spike files, so it counts them here, for the resource estimate.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np

from obi_one.scientific.library.circuit_synapses import SUBSET_FACTOR

# Node ids read at once from a spike file, 8 bytes each.
CHUNK = 1_000_000


@dataclass
class ReplayCounts:
    """What the spike files of a simulation replay.

    Attributes:
        sources: The distinct nodes that spike, by population, over all the files.
        spikes: The spikes of all the files.
    """

    sources: dict[str, int] = field(default_factory=dict)
    spikes: int = 0


def count_replay(spike_files: Iterable[Path], population_sizes: dict[str, int]) -> ReplayCounts:
    """The spiking nodes and the spikes of SONATA spike files.

    A node spiking in several files counts once. Node ids are read in chunks into a mask of the
    population, so memory does not grow with the spikes.

    Args:
        spike_files: The ``spikes`` HDF5 files of the replay inputs.
        population_sizes: The nodes of each population of the circuit.
    """
    masks: dict[str, np.ndarray] = {}
    counts = ReplayCounts()
    for path in spike_files:
        with h5py.File(path, "r") as f:
            for population, group in f.get("spikes", {}).items():
                node_ids = group["node_ids"]
                counts.spikes += node_ids.shape[0]
                size = population_sizes.get(population)
                if size is None:
                    continue
                mask = masks.setdefault(population, np.zeros(size, dtype=bool))
                for start in range(0, node_ids.shape[0], CHUNK):
                    ids = node_ids[start : start + CHUNK].astype(np.int64)
                    mask[ids[(ids >= 0) & (ids < size)]] = True
    counts.sources = {population: int(mask.sum()) for population, mask in masks.items()}
    return counts


def replayed_synapses(
    synapses_by_source: dict[str, float],
    replay: ReplayCounts,
    population_sizes: dict[str, int],
) -> int:
    """The synapses whose source spikes, estimated from the share of each population that spikes.

    The share of a population's synapses that its spiking nodes hold is taken as their share of its
    nodes, times ``SUBSET_FACTOR``, up to all of them: a neuron set of sources is not always drawn
    at random, and the sources that project onto the simulated cells hold more than their share.
    """
    total = 0.0
    for source, synapses in synapses_by_source.items():
        size = population_sizes.get(source)
        if size:
            total += synapses * min(1.0, SUBSET_FACTOR * replay.sources.get(source, 0) / size)
    return round(total)
