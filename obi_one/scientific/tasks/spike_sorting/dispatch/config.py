from enum import StrEnum
from typing import ClassVar
from pathlib import Path

from pydantic import Field
from entitysdk import Client
from entitysdk.models import Entity, TaskConfig
from entitysdk.types import TaskActivityType, TaskConfigType

from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.tasks.spike_sorting.dispatch.blocks import (
    DispatchBasic,
    DispatchDataDependent,
    DispatchDebug,
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
    single_coord_class_name: ClassVar[str] = "AINDEPhysDispatchSingleConfig"
    name: ClassVar[str] = "Multi Electrode Recording Postprocessing"
    description: ClassVar[str] = "Spike sorting preprocessing configuration."

    json_schema_extra_additions: ClassVar[dict] = {
        "ui_enabled": False,
        "group_order": [BlockGroup.SETUP, BlockGroup.PREPROCESSING, BlockGroup.SPIKE_SORTING],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:
        return []

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

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: Client = None,
    ):
        pass

    def create_campaign_generation_entity(self, generated: list, db_client: Client) -> None:
        pass


class AINDEPhysDispatchSingleConfig(AINDEPhysDispatchScanConfig, SingleConfigMixin):
    """SpikeSortingPreprocessingSingleConfig."""

    """Description."""

    def create_single_entity_with_config(
        self,
        campaign: TaskConfig,
        db_client: Client,
    ):
        pass

    def command_line_representation(self) -> str:
        """ADVANCED OPTIONS:
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

        command_str += (
            f" --no-split-segments={not self.dispatch_basic.split_segments}"
        )
        command_str += f" --no-split-groups={not self.dispatch_basic.split_groups}"
        command_str += (
            f" --skip-timestamps-check={self.dispatch_basic.skip_timestamps_check}"
        )
        command_str += (
            f" --min-recording-duration={self.dispatch_basic.min_recording_duration}"
        )

        command_str += f" --debug={self.dispatch_debug.debug_mode}"
        command_str += f" --debug-duration={self.dispatch_debug.debug_duration}"

        command_str += f" --input={self.dispatch_data_dependent.input_format}"
        command_str += (
            f" --multi-session={self.dispatch_data_dependent.multi_session_data}"
        )

        return command_str
