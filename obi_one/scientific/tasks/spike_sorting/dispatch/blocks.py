from pathlib import Path
from typing import Literal

from pydantic import Field, PositiveFloat

from obi_one.core.block import Block

# Preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing/blob/main/code/params.json


class SpikeSortingSetupBasic(Block):
    """SpikeSortingSetupBasic."""

    recording: Path | list[Path] = Field(
        default=Path(),
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
        unit="s",
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

class SpikeInterfaceDataDependent(Block):
    """SpikeInterfaceDataDependent."""

    reader_type: Literal['plexon', 'neuralynx', 'intan'] = Field(
        default="plexon",
        title="Reader type",
        description="Type of the reader to use.",
    )
    reader_kwargs: dict | list[dict] = Field(
        default_factory=dict,
        title="Reader kwargs",
        description="Keyword arguments for the reader.",
    )
    keep_or_skip_stream_substrings_mode: Literal['keep', 'skip'] = Field(
        default="keep",
        title="Keep or skip stream substrings mode",
        description="Whether the substrings in substrings_to_skip_or_keep should be kept or skipped"
    )
    substrings_to_skip_or_keep: tuple[str] = Field(
        default=None,
        title="Skip or keep stream substrings",
        description="Whether to specify stream substrings to skip or keep. Should be a tuple with two elements: (mode, substrings), where mode is either 'skip' or 'keep' and substrings is a string or list of strings with the substrings to skip or keep.",
    )
    # probe_paths: tuple[str] | tuple[None] = Field(
    #     title="Probe paths",
    #     description="Paths to the probe files. Only used if reader_type is 'spikeinterface'.",
    # )
    # session_names: tuple[str] = Field(
    #     title="Session names",
    #     description="List of session names to process. Only used if multi-session data is True.",
    # )

    def command_line_representation(self) -> str:
        command_line_str = ""

        if self.reader_kwargs:
            command_line_str += f" --spikeinterface-reader-kwargs='{self.reader_kwargs}'"

        if self.keep_or_skip_stream_substrings_mode == "keep":
            command_line_str += f" --spikeinterface-keep-stream-substrings='{self.substrings_to_skip_or_keep}'"
        elif self.keep_or_skip_stream_substrings_mode == "skip":
            command_line_str += f" --spikeinterface-skip-stream-substrings='{self.substrings_to_skip_or_keep}'"

        # if self.probe_paths:
        #     command_line_str += f" --spikeinterface-probe-paths='{self.probe_paths}'"

        # if self.session_names:
        #     command_line_str += f" --spikeinterface-session-names='{self.session_names}'"

        return command_line_str



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
        unit="s",
    )
