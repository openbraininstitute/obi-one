from typing import Literal

from pydantic import Field, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units

# Job Dispatch
# https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch
# Preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing/blob/main/code/params.json


class DispatchBasic(Block):
    """Top-level dispatch flags shared across all input formats."""

    split_segments: bool = Field(
        default=True,
        title="Split segments",
        description="Whether to split segments in the recording.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    split_groups: bool = Field(
        default=True,
        title="Split groups",
        description="Whether to split groups in the recording.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    skip_timestamps_check: bool = Field(
        default=False,
        title="Skip timestamps check",
        description="Whether to skip the timestamps monotonicity check.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    min_recording_duration: float | list[float] = Field(
        default=-1.0,
        title="Minimum recording duration",
        description="Minimum duration of the recording in seconds. -1 disables filtering.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.SECONDS,
        },
    )


class SpikeInterfaceInfo(Block):
    """Configuration passed to dispatch as the ``--spikeinterface-info`` JSON.

    The dispatch script (aind-ephys-job-dispatch) reads:
      - reader_type (required)
      - reader_kwargs (optional)
      - keep_stream_substrings (optional, mutually exclusive with skip)
      - skip_stream_substrings (optional, mutually exclusive with keep)
      - probe_paths (optional)
      - session_names (optional)
    """

    reader_type: str = Field(
        default="binaryfolder",
        title="Reader type",
        description=(
            "SpikeInterface reader key (e.g. 'binaryfolder', 'spikeglx', 'openephysbinary', "
            "'plexon', 'neuralynx', 'intan'). Must be a key of "
            "spikeinterface.extractors.recording_extractor_full_dict."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    reader_kwargs: dict | list[dict] = Field(
        default_factory=dict,
        title="Reader kwargs",
        description="Keyword arguments for the reader. Dict for single session, list for multi.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    keep_stream_substrings: str | list[str] | None = Field(
        default=None,
        title="Keep stream substrings",
        description="Stream name substring(s) to load. Mutually exclusive with skip.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    skip_stream_substrings: str | list[str] | None = Field(
        default=None,
        title="Skip stream substrings",
        description="Stream name substring(s) to skip. Mutually exclusive with keep.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    probe_paths: str | dict | list | None = Field(
        default=None,
        title="Probe paths",
        description="Path(s) to a ProbeInterface JSON file. String, dict, or list.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    session_names: str | list[str] | None = Field(
        default=None,
        title="Session names",
        description="Session identifier(s) when running multi-session.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    def to_dict(self) -> dict:
        """Build the dict serialised into the ``--spikeinterface-info`` argument."""
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
    """Input-format-dependent dispatch options."""

    multi_session_data: bool = Field(
        default=False,
        title="Multi-session data",
        description="Whether the data is multi-session.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    input_format: Literal["aind", "spikeglx", "openephys", "nwb", "spikeinterface"] = Field(
        default="aind",
        title="Input format",
        description="Format of the input data.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )

    spikeinterface_info: SpikeInterfaceInfo | None = Field(
        default=None,
        title="SpikeInterface info",
        description="Required when input_format == 'spikeinterface'.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    nwb_files: str | None = Field(
        default=None,
        title="NWB files",
        description="Comma-separated NWB file paths. Only used when input_format == 'nwb'.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )


class DispatchDebug(Block):
    """Debug-mode dispatch options."""

    debug_mode: bool | list[bool] = Field(
        default=False,
        title="Debug mode",
        description="Whether to run in debug mode.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    debug_duration: PositiveFloat | list[PositiveFloat] = Field(
        default=30.0,
        title="Debug mode duration",
        description="Duration for debug mode in seconds. Only used if debug_mode is True.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.SECONDS,
        },
    )
