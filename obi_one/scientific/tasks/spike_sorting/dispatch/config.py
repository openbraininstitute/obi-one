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

from obi_one.scientific.tasks.spike_sorting.dispatch.blocks import (
    DispatchBasic,
    DispatchDebug,
    DispatchDataDependent,
)



# Job Dispatch
# https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch/

# Preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing/blob/main/code/params.json


class BlockGroup(StrEnum):
    """SpikeSorting Block Group."""

    SETUP = "Setup"
    PREPROCESSING = "Preprocessing"
    SPIKE_SORTING = "Spike sorting"

class AINDEPhysDispatchScanConfig(ScanConfig):

    single_coord_class_title: ClassVar[str] = "SpikeSortingPreprocessingSingleConfig"
    title: ClassVar[str] = "Multi Electrode Recording Postprocessing"
    description: ClassVar[str] = (
        "Spike sorting preprocessing configuration."
    )

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "block_block_group_order": [
                BlockGroup.SETUP,
                BlockGroup.PREPROCESSING,
                BlockGroup.SPIKE_SORTING,
            ],
        }


    dispatch_basic: DispatchBasic = Field(
        title="Recording setup",
        description="Recording setup.",
        group=BlockGroup.SETUP,
        group_order=0,
    )

    dispatch_data_dependent: DispatchDataDependent = Field(
        title="Data dependent options",
        description="Data dependent options.",
        group=BlockGroup.SETUP,
        group_order=1,
    )

    dispatch_debug: DispatchDebug = Field(
        title="Debug setup",
        description="Debug setup.",
        group=BlockGroup.SETUP,
        group_order=1,
    )


class AINDEPhysDispatchSingleConfig(AINDEPhysDispatchScanConfig, SingleCoordMixin):
    """SpikeSortingPreprocessingSingleConfig."""

    def command_line_representation(self) -> str:
        """
        ADVANCED OPTIONS:
        --no-split-segments       Whether to concatenate or split recording segments or not. Default: split segments
        --no-split-groups         Whether to process different groups separately
        --skip-timestamps-check   Skip timestamps check
        --debug                   Whether to run in DEBUG mode
        --debug-duration          Duration of clipped recording in debug mode. Default is 30 seconds. 
                                    Only used if debug is enabled
        --min-recording-duration  Minimum duration of the recording in seconds. Recordings shorter than this will be skipped. Default: -1 (no minimum duration)
        
        # DATA DEPENDEDNT OPTIONS
        --input {aind,spikeglx,openephys,nwb,spikeinterface}
                                    Which 'loader' to use (aind | spikeglx | openephys | nwb | spikeinterface)
        --multi-session           Whether the data folder includes multiple sessions or not. Default: False
        

        # ONLY USED IF --input spikeinterface
        --spikeinterface-info     A JSON path or string to specify how to parse the recording in spikeinterface including: 
                                    - 1. reader_type (required): string with the reader type (e.g. 'plexon', 'neuralynx', 'intan' etc.).
                                    - 2. reader_kwargs (optional): dictionary with the reader kwargs (e.g. {'folder': '/path/to/folder'}).
                                    - 3. keep_stream_substrings (optional): string or list of strings with the stream names to load (e.g. 'AP' or ['AP', 'LFP']).
                                    - 4. skip_stream_substrings (optional): string (or list of strings) with substrings used to skip streams (e.g. 'NIDQ' or ['USB', 'EVENTS']).
                                    - 5. probe_paths (optional): string or dict the probe paths to a ProbeInterface JSON file (e.g. '/path/to/probe.json'). If a dict is provided, the key is the stream name and the value is the probe path. If reader_kwargs is not provided, the reader will be created with default parameters. The probe_path is required if the reader doesn't load the probe automatically.
        """

        command_str = "python code/run"
        if not self.single_config.dispatch_advanced.split_segments:
            command_str += " --no-split-segments"
        if not self.single_config.dispatch_advanced.split_groups:
            command_str += " --no-split-groups"
        if self.single_config.dispatch_advanced.skip_timestamps_check:
            command_str += " --skip-timestamps-check"
        if self.single_config.dispatch_advanced.min_recording_duration > 0:
            command_str += f" --min-recording-duration {self.single_config.dispatch_advanced.min_recording_duration}"

        command_str += " --debug" if self.single_config.dispatch_advanced.debug_mode else ""
        command_str += f" --debug-duration {self.single_config.dispatch_advanced.debug_duration}" if self.single_config.dispatch_advanced.debug_mode else ""

        # DATA DEPENDEDNT OPTIONS (Depends on the input data)
        INPUT = "NWB"
        command_str += f" --input {INPUT}"

        IS_MULTI_SESSION = False
        if IS_MULTI_SESSION:
            command_str += " --multi-session"


