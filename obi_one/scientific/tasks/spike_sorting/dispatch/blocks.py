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
        default=True,
        title="Split segments",
        description="Whether to split segments in the recording.",
    )

    split_groups: bool = Field(
        default=True,
        title="Split groups",
        description="Whether to split groups in the recording.",
    )

    skip_timestamps_check: bool = Field(
        default=False,
        title="Skip timestamps check",
        description="Whether to skip timestamps check.",
    )

    min_recording_duration: float | list[float] = Field(
        default=-1.0,
        title="Minimum recording duration",
        description="Minimum duration of the recording in seconds. -1 disables filtering.",
        unit="s",
    )


class SpikeInterfaceInfo(Block):
    """Configuration passed to dispatch as `--spikeinterface-info` JSON.

    The dispatch script (aind-ephys-job-dispatch) reads:
      - reader_type (required)
      - reader_kwargs (optional)
      - keep_stream_substrings or skip_stream_substrings (optional, mutually exclusive)
      - probe_paths (optional)
      - session_names (optional)
    """

    reader_type: str = Field(
        default="binaryfolder",
        title="Reader type",
        description=(
            "SpikeInterface reader key (e.g. 'binaryfolder', 'spikeglx', 'openephysbinary', "
            "'plexon', 'neuralynx', 'intan'). Must be a key of "
            "`spikeinterface.extractors.recording_extractor_full_dict`."
        ),
    )
    reader_kwargs: dict | list[dict] = Field(
        default_factory=dict,
        title="Reader kwargs",
        description="Keyword arguments for the reader. Dict for single session, list for multi.",
    )
    keep_stream_substrings: str | list[str] | None = Field(
        default=None,
        title="Keep stream substrings",
        description="Stream name substring(s) to load. Mutually exclusive with skip.",
    )
    skip_stream_substrings: str | list[str] | None = Field(
        default=None,
        title="Skip stream substrings",
        description="Stream name substring(s) to skip. Mutually exclusive with keep.",
    )
    probe_paths: str | dict | list | None = Field(
        default=None,
        title="Probe paths",
        description="Path(s) to a ProbeInterface JSON file. String, dict, or list.",
    )
    session_names: str | list[str] | None = Field(
        default=None,
        title="Session names",
        description="Session identifier(s) when running multi-session.",
    )

    def to_dict(self) -> dict:
        """Build the dict serialized into the --spikeinterface-info argument."""
        info: dict = {"reader_type": self.reader_type, "reader_kwargs": self.reader_kwargs}
        if self.keep_stream_substrings is not None:
            info["keep_stream_substrings"] = self.keep_stream_substrings
        if self.skip_stream_substrings is not None:
            info["skip_stream_substrings"] = self.skip_stream_substrings
        if self.probe_paths is not None:
            info["probe_paths"] = self.probe_paths
        if self.session_names is not None:
            info["session_names"] = self.session_names
        return info


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

    spikeinterface_info: SpikeInterfaceInfo | None = Field(
        default=None,
        title="SpikeInterface info",
        description="Required when input_format == 'spikeinterface'.",
    )

    nwb_files: str | None = Field(
        default=None,
        title="NWB files",
        description="Comma-separated NWB file paths. Only used when input_format == 'nwb'.",
    )


class DispatchDebug(Block):
    """DispatchDebug."""

    debug_mode: bool | list[bool] = Field(
        default=False,
        title="Debug mode",
        description="Whether to run in debug mode.",
    )

    debug_duration: PositiveFloat | list[PositiveFloat] = Field(
        default=30.0,
        title="Debug mode duration",
        description="Duration for debug mode in seconds.",
        unit="s",
    )
