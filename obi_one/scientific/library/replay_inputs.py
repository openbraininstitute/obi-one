"""Count the sources and spikes of a simulation's replay spike files.

See docs/circuit-simulation-resources.md.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np

from obi_one.scientific.library.circuit_synapses import WORST_CASE_SUBSET_DENSITY_VS_AVERAGE

CHUNK = 1_000_000


@dataclass
class ReplayCounts:
    """Sources and spikes found in a simulation's replay spike files.

    Attributes:
        sources: Number of distinct spiking nodes, by population.
        spikes: Total number of spikes in all the files.
    """

    sources: dict[str, int] = field(default_factory=dict)
    spikes: int = 0


def count_replay(spike_files: Iterable[Path], population_sizes: dict[str, int]) -> ReplayCounts:
    """Count the spiking nodes and the spikes in SONATA spike files, reading them in chunks.

    Args:
        spike_files: Spike files of the replay inputs.
        population_sizes: Number of nodes in each population of the circuit.
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
    replayed_sources: dict[str, int],
    population_sizes: dict[str, int],
) -> int:
    """Estimate the synapses with a spiking source, from each source's share of spiking nodes."""
    total = 0.0
    for source, synapses in synapses_by_source.items():
        if size := population_sizes.get(source):
            total += synapses * min(
                1.0, WORST_CASE_SUBSET_DENSITY_VS_AVERAGE * replayed_sources.get(source, 0) / size
            )
    return round(total)
