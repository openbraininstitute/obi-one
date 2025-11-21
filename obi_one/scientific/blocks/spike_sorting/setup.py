from obi_one.core.block import Block
from obi_one.core.task import Task
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleCoordMixin
from pydantic import Discriminator
from pathlib import Path
from enum import StrEnum
from pydantic import Field, PositiveInt, PositiveFloat, NonNegativeInt, NonNegativeFloat
from typing import Annotated, ClassVar, Literal
import numpy as np

# Job Dispatch
# https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch/

# Preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing/blob/main/code/params.json



class SpikeSortingSetupRecording(Block):
    """SpikeSortingSetupRecording."""

    recording: Path | list[Path] = Field(
        default=Path(""),
        title="Recording path",
        description="Path to the recording file.",
    )

    test_mode: bool | list[bool] = Field(
        default=False,
        title="Test mode",
        description="Whether to run in test mode.",
    )

    test_mode_duration: PositiveFloat | list[PositiveFloat] = Field(
        default=60.0,
        title="Test mode duration",
        description="Duration for test mode in seconds.",
        unit="s"
    )

class SpikeSortingSetupAdvanced(Block):
    """SpikeSortingSetupAdvanced."""

    split_segments: bool | list[bool] = Field(
        default=False,
        title="Split segments",
        description="Whether to split segments in the recording.",
    )

    split_groups: bool | list[bool] = Field(
        default=False,
        title="Split groups",
        description="Whether to split groups in the recording.",
    )

    skip_timestamps_check: bool | list[bool] = Field(
        default=False,
        title="Skip timestamps check",
        description="Whether to skip timestamps check.",
    )

    multi_session_data: bool | list[bool] = Field(
        default=False,
        title="Multi-session data",
        description="Whether the data is multi-session.",
    )
