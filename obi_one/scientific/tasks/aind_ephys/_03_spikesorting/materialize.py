"""Toy input for the spike sorting stage when it is given no preprocessing output."""

import logging
from pathlib import Path

from obi_one.scientific.tasks.aind_ephys._02_preprocessing.blocks import MotionCorrection
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.config import (
    AINDEPhysPreprocessingSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.task import AINDEPhysPreprocessingTask
from obi_one.scientific.tasks.aind_ephys.toy_recording import write_toy_nwb

L = logging.getLogger(__name__)


def materialize_preprocessing_output(folder: Path) -> Path:
    """Write a toy NWB recording into ``folder`` and preprocess it.

    Returns the preprocessing output folder, laid out as the spike sorting stage reads it.
    """
    L.info("Making a toy recording to sort under %s.", folder)
    nwb_path = folder / "toy_recording.nwb"
    write_toy_nwb(nwb_path)

    preprocessing = AINDEPhysPreprocessingSingleConfig(
        initialize=AINDEPhysPreprocessingSingleConfig.Initialize(
            nwb_path=nwb_path,
            min_preprocessing_duration=0.0,
        ),
        motion_correction=MotionCorrection(compute=False),
    )
    preprocessing.coordinate_output_root = folder / "preprocessing"
    return AINDEPhysPreprocessingTask(config=preprocessing).execute()
