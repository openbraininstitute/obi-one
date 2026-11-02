"""Toy input for the spike sorting stage when it is given no preprocessing output."""

import logging
from pathlib import Path

from obi_one.scientific.tasks.aind_ephys._01_dispatch.config import AINDEPhysDispatchSingleConfig
from obi_one.scientific.tasks.aind_ephys._01_dispatch.task import AINDEPhysDispatchTask
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.blocks import MotionCorrection
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.config import (
    AINDEPhysPreprocessingSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.task import AINDEPhysPreprocessingTask
from obi_one.scientific.tasks.aind_ephys.toy_recording import write_toy_nwb

L = logging.getLogger(__name__)


def materialize_preprocessing_output(folder: Path) -> Path:
    """Write a toy NWB recording into ``folder``, dispatch and preprocess it.

    Returns the preprocessing output folder, laid out as the spike sorting stage reads it.
    """
    L.info("Making a toy recording to sort under %s.", folder)
    nwb_path = folder / "toy_recording.nwb"
    write_toy_nwb(nwb_path)

    dispatch = AINDEPhysDispatchSingleConfig(
        initialize=AINDEPhysDispatchSingleConfig.Initialize(nwb_path=nwb_path),
    )
    dispatch.coordinate_output_root = folder / "dispatch"
    AINDEPhysDispatchTask(config=dispatch).execute()

    preprocessing = AINDEPhysPreprocessingSingleConfig(
        initialize=AINDEPhysPreprocessingSingleConfig.Initialize(
            dispatch_output_path=dispatch.coordinate_output_root,
            min_preprocessing_duration=0.0,
        ),
        motion_correction=MotionCorrection(compute=False),
    )
    preprocessing.coordinate_output_root = folder / "preprocessing"
    return AINDEPhysPreprocessingTask(config=preprocessing).execute()
