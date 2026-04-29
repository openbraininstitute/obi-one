from obi_one.core.block import Block
from pydantic import Field, PositiveFloat
from typing import Annotated, Literal
import numpy as np
from pathlib import Path


# Preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing/blob/main/code/params.json

class SpikeSortingSetupBasic(Block):
    """SpikeSortingSetupBasic."""

    recording: Path | list[Path] = Field(
        default=Path(""),
        title="Recording path",
        description="Path to the recording file.",
    )

class DispatchBasic(Block):
    """DispatchBasic."""

    split_segments: bool = Field(
        default=False,
        title="Split segments",
        description="Whether to split segments in the recording.",
    )

    split_groups: bool = Field(
        default=False,
        title="Split groups",
        description="Whether to split groups in the recording.",
    )

    skip_timestamps_check: bool = Field(
        default=False,
        title="Skip timestamps check",
        description="Whether to skip timestamps check.",
    )

    min_recording_duration: PositiveFloat | list[PositiveFloat] = Field(
        default=0.0,
        title="Minimum recording duration",
        description="Minimum duration of the recording in seconds.",
        unit="s"
    )

class DispatchDataDependent(Block):
    """DispatchDataDependent."""
    multi_session_data: bool = Field(
        default=False,
        title="Multi-session data",
        description="Whether the data is multi-session.",
    )

    input_format: Literal["aind", "spikeglx", "openephys", "nwb", "spikeinterface"] = Field(
        default="aind",
        title="Input format",
        description="Format of the input data.",
    )

    

class DispatchDebug(Block):
    """DispatchDebug."""

    debug_mode: bool | list[bool] = Field(
        default=False,
        title="Debug mode",
        description="Whether to run in debug mode.",
    )

    debug_duration: PositiveFloat | list[PositiveFloat] = Field(
        default=60.0,
        title="Debug mode duration",
        description="Duration for debug mode in seconds.",
        unit="s"
    )