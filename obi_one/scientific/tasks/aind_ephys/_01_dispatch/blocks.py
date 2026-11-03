"""Settings of the dispatch step, shared by the dispatch and preprocessing stages."""

from pydantic import Field, NonNegativeFloat, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


class JobDispatch(Block):
    """How the raw recordings of an NWB file are split into jobs."""

    electrical_series_path: str | None = Field(
        default=None,
        title="Electrical series",
        description=(
            "Path of the one ElectricalSeries to process, such as"
            " 'acquisition/ElectricalSeriesAP'. None processes every series in acquisition."
        ),
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    split_segments: bool = Field(
        default=True,
        title="Split segments",
        description="Whether each recording segment becomes its own job.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    split_groups: bool = Field(
        default=True,
        title="Split groups",
        description="Whether each channel group (probe or shank) becomes its own job.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    skip_timestamps_check: bool = Field(
        default=False,
        title="Skip timestamps check",
        description="Skip the check that resets timestamps with gaps or reversals.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    min_recording_duration: NonNegativeFloat | None = Field(
        default=None,
        title="Minimum recording duration",
        description="Recordings shorter than this are not dispatched. None keeps them all.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True, SchemaKey.UNITS: Units.SECONDS},
    )
    min_sampling_frequency: PositiveFloat = Field(
        default=10_000.0,
        title="Minimum sampling frequency",
        description="Series sampled below this are taken to be LFP and skipped.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True, SchemaKey.UNITS: Units.HERTZ},
    )
    debug: bool = Field(
        default=False,
        title="Debug",
        description="Clip each segment to the debug duration, and keep short recordings.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    debug_duration: PositiveFloat = Field(
        default=30.0,
        title="Debug duration",
        description="Duration each segment is clipped to in debug mode.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True, SchemaKey.UNITS: Units.SECONDS},
    )
