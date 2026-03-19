from pathlib import Path
from typing import ClassVar

import numpy as np
from pydantic import NonNegativeFloat

from obi_one.scientific.blocks.stimuli.spike.base import SpikeStimulus
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.unions.unions_timestamps import (
    resolve_timestamps_ref_to_timestamps_block,
)


class FullySynchronousSpikeStimulus(SpikeStimulus):
    """Spikes sent at the same time.

    Sent from all neurons in the source neuron set to efferently connected

    When using repeated timestamps (i.e. Regular Timestamps), stimulus durations
    should be small enough such that stimulus periods do not overlap across
    repetitions of the same stimulus.
    """

    title: ClassVar[str] = "Fully Synchronous Spikes (Efferent)"

    _module: str = "synapse_replay"
    _input_type: str = "spikes"

    def generate_spikes(
        self,
        circuit: Circuit,
        spike_file_path: Path,
        simulation_length: NonNegativeFloat,
        source_node_population: str | None = None,
    ) -> None:
        self._simulation_length = simulation_length
        gids = self.source_neuron_set.block.get_neuron_ids(circuit, source_node_population)
        source_node_population = self.source_neuron_set.block.get_population(source_node_population)
        gid_spike_map = {}
        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )

        for start_time in timestamps_block.timestamps():
            spike = [start_time + self.timestamp_offset]
            for gid in gids:
                if gid in gid_spike_map:
                    gid_spike_map[gid] += spike
                else:
                    gid_spike_map[gid] = spike
        self._spike_file = f"{self.block_name}_spikes.h5"
        self.write_spike_file(
            gid_spike_map, spike_file_path / self._spike_file, source_node_population
        )
