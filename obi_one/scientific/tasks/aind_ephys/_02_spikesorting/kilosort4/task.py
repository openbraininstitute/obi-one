"""Spike sorting stage with Kilosort4."""

from pathlib import Path

import numpy as np
import spikeinterface as si

from obi_one.scientific.tasks.aind_ephys._02_spikesorting.kilosort4.config import (
    AINDEPhysSpikeSortingKilosort4SingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._02_spikesorting.task import AINDEPhysSpikeSortingTask


class AINDEPhysSpikeSortingKilosort4Task(AINDEPhysSpikeSortingTask):
    """Sort every recording of the preprocessing stage with Kilosort4."""

    config: AINDEPhysSpikeSortingKilosort4SingleConfig

    @staticmethod
    def sorter_motion(sorter_output_folder: Path, recording: si.BaseRecording) -> si.Motion:
        """The motion Kilosort4 estimated, from its ``ops.npy``."""
        ops = np.load(sorter_output_folder / "ops.npy", allow_pickle=True).item()
        displacement = ops["dshift"]
        t_bin = ops["batch_size"] / ops["fs"]
        temporal_bins_s = np.linspace(
            recording.get_start_time() + t_bin / 2,
            recording.get_end_time() - t_bin / 2,
            displacement.shape[0],
        )
        return si.Motion(
            displacement=displacement, temporal_bins_s=temporal_bins_s, spatial_bins_um=ops["yblk"]
        )
