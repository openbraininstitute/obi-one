from collections import defaultdict
from typing import ClassVar

from obi_one.scientific.blocks.stimuli.spike.base import SpikeStimulus


class FullySynchronousSpikeStimulus(SpikeStimulus):
    """Spikes sent at the same time.

    Sent from all neurons in the source neuron set to efferently connected

    When using repeated timestamps (i.e. Regular Timestamps), stimulus durations
    should be small enough such that stimulus periods do not overlap across
    repetitions of the same stimulus.
    """

    title: ClassVar[str] = "Fully Synchronous Spikes (Efferent)"

    def generate_spikes_by_gid(self, source_gids: list[int]) -> dict[int, list[float]]:
        spike_times = self._offset_timestamps()
        spikes_by_gid: dict[int, list[float]] = defaultdict(list)
        for gid in source_gids:
            spikes_by_gid[gid] = list(spike_times)
        return spikes_by_gid
