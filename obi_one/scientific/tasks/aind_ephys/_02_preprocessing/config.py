"""ScanConfig for the aind-ephys-preprocessing capsule."""

from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal

from entitysdk import Client
from entitysdk.models import Entity, TaskConfig
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.units import Units
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.blocks import (
    BandpassFilterParams,
    CommonReference,
    DetectBadChannels,
    HighpassFilterParams,
    HighpassSpatialFilter,
    JobKwargs,
    MotionCorrection,
    PhaseShift,
)


class BlockGroup(StrEnum):
    """Preprocessing block groups."""

    SETUP = "Setup"
    PREPROCESSING = "Preprocessing"


class AINDEPhysPreprocessingScanConfig(ScanConfig):
    """ScanConfig wrapping the aind-ephys-preprocessing CLI.

    The capsule's ``code/run_capsule.py`` consumes ``job_*.json`` files
    (produced by the dispatch stage) from ``../data/`` and writes preprocessed
    recordings + metadata to ``../results/``. The ``initialize.dispatch_output_path``
    field tells the OBI-side task where to seed those job files from.
    """

    single_coord_class_name: ClassVar[str] = "AINDEPhysPreprocessingSingleConfig"
    name: ClassVar[str] = "AIND Ephys Preprocessing"
    description: ClassVar[str] = (
        "Run the aind-ephys-preprocessing capsule on dispatched ephys job(s)."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.PREPROCESSING],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:  # noqa: ARG002, PLR6301
        return []

    class Initialize(Block):
        """Top-level CLI / control parameters for the preprocessing capsule."""

        dispatch_output_path: Path = Field(
            title="Dispatch output path",
            description=(
                "Directory containing one or more ``job_*.json`` files produced by"
                " the aind-ephys-job-dispatch stage. Every job JSON in this folder"
                " is copied into the capsule's data folder before the run."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

        denoising_strategy: Literal["cmr", "destripe"] = Field(
            default="cmr",
            title="Denoising strategy",
            description="Denoising strategy.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
        )
        filter_type: Literal["highpass", "bandpass"] = Field(
            default="highpass",
            title="Filter type",
            description="Whether to apply a highpass or a bandpass filter.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
        )

        min_preprocessing_duration: float | list[float] = Field(
            default=120.0,
            title="Minimum preprocessing duration",
            description=(
                "Recordings shorter than this duration (in seconds) are skipped"
                " unless the dispatcher's debug flag is set."
            ),
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.SECONDS,
            },
        )

        remove_out_channels: bool = Field(
            default=True,
            title="Remove out channels",
            description="Whether to remove channels detected as outside the brain.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )
        remove_bad_channels: bool = Field(
            default=True,
            title="Remove bad channels",
            description="Whether to remove channels detected as bad.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )
        max_bad_channel_fraction: float | list[float] = Field(
            default=0.5,
            title="Max bad channel fraction",
            description=("Fail the recording if more than this fraction of channels are bad."),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )

        t_start: float | None = Field(
            default=None,
            title="t_start",
            description="Clip the recording to start at this time (seconds).",
            json_schema_extra={SchemaKey.UI_HIDDEN: True},
        )
        t_stop: float | None = Field(
            default=None,
            title="t_stop",
            description="Clip the recording to stop at this time (seconds).",
            json_schema_extra={SchemaKey.UI_HIDDEN: True},
        )

        n_jobs: int = Field(
            default=1,
            title="n_jobs",
            description="Parallel job count (-1 for all cores).",
            json_schema_extra={SchemaKey.UI_HIDDEN: True},
        )

    initialize: Initialize = Field(
        title="Initialize",
        description="Top-level control parameters for the preprocessing run.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    job_kwargs: JobKwargs = Field(
        default_factory=JobKwargs,
        title="Job kwargs",
        description="SpikeInterface job_kwargs.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    phase_shift: PhaseShift = Field(
        default_factory=PhaseShift,
        title="Phase shift",
        description="Phase-shift block.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.PREPROCESSING,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    highpass_filter: HighpassFilterParams = Field(
        default_factory=HighpassFilterParams,
        title="Highpass filter",
        description="Highpass-filter parameters (used when filter_type='highpass').",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.PREPROCESSING,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    bandpass_filter: BandpassFilterParams = Field(
        default_factory=BandpassFilterParams,
        title="Bandpass filter",
        description="Bandpass-filter parameters (used when filter_type='bandpass').",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.PREPROCESSING,
            SchemaKey.GROUP_ORDER: 2,
        },
    )

    detect_bad_channels: DetectBadChannels = Field(
        default_factory=DetectBadChannels,
        title="Detect bad channels",
        description="Bad-channel detection parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.PREPROCESSING,
            SchemaKey.GROUP_ORDER: 3,
        },
    )

    common_reference: CommonReference = Field(
        default_factory=CommonReference,
        title="Common reference",
        description="Common-reference parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.PREPROCESSING,
            SchemaKey.GROUP_ORDER: 4,
        },
    )

    highpass_spatial_filter: HighpassSpatialFilter = Field(
        default_factory=HighpassSpatialFilter,
        title="Highpass spatial filter",
        description="Spatial-filter parameters (used by 'destripe' denoising).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.PREPROCESSING,
            SchemaKey.GROUP_ORDER: 5,
        },
    )

    motion_correction: MotionCorrection = Field(
        default_factory=MotionCorrection,
        title="Motion correction",
        description="Motion-correction parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.PREPROCESSING,
            SchemaKey.GROUP_ORDER: 6,
        },
    )

    def create_campaign_entity_with_config(
        self,
        output_root: Path,  # noqa: ARG002
        multiple_value_parameters_dictionary: dict | None = None,  # noqa: ARG002
        db_client: Client = None,  # noqa: ARG002
    ) -> None:
        return None

    def create_campaign_generation_entity(
        self,
        generated: list,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None


class AINDEPhysPreprocessingSingleConfig(AINDEPhysPreprocessingScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`AINDEPhysPreprocessingScanConfig`."""

    def create_single_entity_with_config(
        self,
        campaign: TaskConfig,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None

    def params_dict(self) -> dict:
        """Build the params.json payload the capsule expects."""
        return {
            "job_kwargs": self.job_kwargs.to_dict(),
            "denoising_strategy": self.initialize.denoising_strategy,
            "filter_type": self.initialize.filter_type,
            "min_preprocessing_duration": self.initialize.min_preprocessing_duration,
            "remove_out_channels": self.initialize.remove_out_channels,
            "remove_bad_channels": self.initialize.remove_bad_channels,
            "max_bad_channel_fraction": self.initialize.max_bad_channel_fraction,
            "phase_shift": self.phase_shift.to_dict(),
            "highpass_filter": self.highpass_filter.to_dict(),
            "bandpass_filter": self.bandpass_filter.to_dict(),
            "detect_bad_channels": self.detect_bad_channels.to_dict(),
            "common_reference": self.common_reference.to_dict(),
            "highpass_spatial_filter": self.highpass_spatial_filter.to_dict(),
            "motion_correction": self.motion_correction.to_dict(),
        }
