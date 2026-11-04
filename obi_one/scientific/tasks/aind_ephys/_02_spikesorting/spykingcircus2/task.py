"""Spike sorting stage with SpykingCircus2."""

from obi_one.scientific.tasks.aind_ephys._02_spikesorting.spykingcircus2.config import (
    AINDEPhysSpikeSortingSpykingCircus2SingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._02_spikesorting.task import AINDEPhysSpikeSortingTask


class AINDEPhysSpikeSortingSpykingCircus2Task(AINDEPhysSpikeSortingTask):
    """Sort every recording of the preprocessing stage with SpykingCircus2."""

    config: AINDEPhysSpikeSortingSpykingCircus2SingleConfig
