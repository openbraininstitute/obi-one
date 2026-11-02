"""Config for the dispatch stage of the AIND ephys pipeline."""

from pathlib import Path
from typing import ClassVar

from pydantic import Field, NonNegativeFloat, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.units import Units


class AINDEPhysDispatchScanConfig(ScanConfig):
    """Split the raw recordings of an NWB file into the jobs the later stages process.

    Port of https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch for NWB input: one job
    per ElectricalSeries in ``acquisition``, split further by segment and probe group.
    """

    name: ClassVar[str] = "AIND Ephys Job Dispatch"
    description: ClassVar[str] = (
        "Splits the extracellular recordings of an NWB file into per-probe spike sorting jobs."
    )

    json_schema_extra_additions: ClassVar[dict] = {SchemaKey.UI_ENABLED: False}

    class Initialize(Block):
        nwb_path: Path = Field(
            title="NWB file",
            description="NWB file whose acquisition holds the raw extracellular recording.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
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

    initialize: Initialize = Field(
        title="Initialize",
        description="The NWB input and how its recordings are split into jobs.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE},
    )


class AINDEPhysDispatchSingleConfig(AINDEPhysDispatchScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`AINDEPhysDispatchScanConfig`."""
