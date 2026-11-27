"""Compute the synapse and replay counts recorded on a Simulation.

See docs/circuit-simulation-resources.md.
"""

from pathlib import Path

import libsonata
from entitysdk.client import Client
from entitysdk.models import Simulation

from obi_one.db_sdk.circuit import circuit_file_opener
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.circuit_staging import SONATA_CIRCUIT_ASSET_SELECTION
from obi_one.scientific.library.circuit_synapses import (
    CellSynapses,
    count_synapses_by_source,
    read_synapses_per_cell,
    staged_synapses_per_cell,
)
from obi_one.scientific.library.constants import SONATA
from obi_one.scientific.library.replay_inputs import count_replay, replayed_synapses


def replay_spike_files(sonata_config: dict, directory: Path) -> list[Path]:
    """Return the spike files of the replay inputs in a SONATA simulation config."""
    return [
        Path(directory, config["spike_file"])
        for config in sonata_config.get("inputs", {}).values()
        if config.get("module") == SONATA.SPIKE_STIMULUS_MODULE and config.get("spike_file")
    ]


def simulation_synapse_counts(
    db_client: Client,
    circuit: CircuitFromID,
    staged: Circuit,
    node_ids: dict[str, list[int]],
    spike_files: list[Path],
) -> dict[str, int]:
    """Count the synapses onto the simulated cells, those with a replayed source, and the spikes.

    Returns only the counts that entitysdk's Simulation has fields for.
    """
    if "number_synapses" not in Simulation.model_fields:
        return {}
    entity = circuit.entity(db_client)
    asset = db_client.select_assets(entity, SONATA_CIRCUIT_ASSET_SELECTION).one()

    def read() -> dict[str, CellSynapses]:
        open_edges_file = None
        if not staged.has_staged_edges:
            open_edges_file = circuit_file_opener(
                db_client,
                entity_id=entity.id,
                asset=asset,
                dest_dir=Path(staged.path).parent.resolve(),
            )
        return read_synapses_per_cell(staged.path, open_edges_file)

    by_source = count_synapses_by_source(
        staged_synapses_per_cell(Path(staged.path), read), node_ids
    )
    replayed, spikes = 0, 0
    if spike_files:
        config = libsonata.CircuitConfig.from_file(staged.path)
        sizes = {pop: config.node_population(pop).size for pop in config.node_populations}
        replay = count_replay(spike_files, sizes)
        replayed, spikes = replayed_synapses(by_source, replay.sources, sizes), replay.spikes
    counts = {
        "number_synapses": round(sum(by_source.values())),
        "number_synapses_in_replay": replayed,
        "number_spikes_in_replay": spikes,
    }
    return {name: n for name, n in counts.items() if name in Simulation.model_fields}
