"""Spike sorting stage with Lupin."""

from obi_one.scientific.tasks.aind_ephys._02_spikesorting.lupin.config import (
    AINDEPhysSpikeSortingLupinSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._02_spikesorting.task import AINDEPhysSpikeSortingTask


class AINDEPhysSpikeSortingLupinTask(AINDEPhysSpikeSortingTask):
    """Sort every recording of the preprocessing stage with Lupin."""

    config: AINDEPhysSpikeSortingLupinSingleConfig
