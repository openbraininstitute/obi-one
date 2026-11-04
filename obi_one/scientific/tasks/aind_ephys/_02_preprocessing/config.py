"""Config for the preprocessing stage of the AIND ephys pipeline."""

from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Self

import entitysdk
from entitysdk.models.entity import Entity
from pydantic import Field, NonNegativeFloat, model_validator

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.units import Units
from obi_one.scientific.from_id.extracellular_recording_from_id import (
    ExtracellularRecordingFromID,
)
from obi_one.scientific.library.info_scan_config.config import (
    BlockGroup as InfoBlockGroup,
    InfoScanConfig,
)
from obi_one.scientific.tasks.aind_ephys._01_dispatch.blocks import JobDispatch
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.blocks import (
    CommonReference,
    DenoisingUnion,
    DetectBadChannels,
    HighpassFilterParams,
    MotionCorrection,
    PhaseShift,
    TemporalFilterUnion,
)
from obi_one.scientific.tasks.aind_ephys.blocks import JobKwargs


class BlockGroup(StrEnum):
    """Preprocessing block groups."""

    PREPROCESSING = "Preprocessing"


class AINDEPhysPreprocessingScanConfig(InfoScanConfig):
    """Split a raw NWB recording into jobs, then filter, denoise and remove bad channels of each.

    The jobs are made as by the dispatch stage and written as ``job_<i>.json`` into the output
    folder, so the recording is staged only once. Port of
    https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing. Writes, for each job,
    the preprocessed traces to ``preprocessed_<name>/``, files to reload them (``binary_<name>``
    and the lazy chain ``preprocessed_<name>``) and the estimated motion to ``motion_<name>/``.
    """

    name: ClassVar[str] = "AIND Ephys Preprocessing"
    description: ClassVar[str] = "Preprocesses a raw extracellular recording."

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [InfoBlockGroup.SETUP_BLOCK_GROUP, BlockGroup.PREPROCESSING],
    }

    class Initialize(Block):
        recording: ExtracellularRecordingFromID | None = Field(
            default=None,
            title="Recording",
            description="Recording entity whose NWB asset holds the raw extracellular traces.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER},
        )
        nwb_path: Path | None = Field(
            default=None,
            title="NWB file",
            description="Local NWB file with the raw recording, instead of a recording entity.",
            json_schema_extra={SchemaKey.UI_HIDDEN: True},
        )
        min_preprocessing_duration: NonNegativeFloat | list[NonNegativeFloat] = Field(
            default=120.0,
            title="Minimum duration",
            description="Shorter recordings are skipped, unless dispatched in debug mode.",
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
            description="Whether to remove channels detected as dead or noisy.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )
        max_bad_channel_fraction: float | list[float] = Field(
            default=0.5,
            title="Max bad channel fraction",
            description="Recordings with at least this fraction of removed channels are skipped.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        t_start: NonNegativeFloat | None = Field(
            default=None,
            title="Start time",
            description="Clip single-segment recordings to start here. Unset starts at 0.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL,
                SchemaKey.UNITS: Units.SECONDS,
            },
        )
        t_stop: NonNegativeFloat | None = Field(
            default=None,
            title="Stop time",
            description="Clip single-segment recordings to stop here. Unset runs to the end.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL,
                SchemaKey.UNITS: Units.SECONDS,
            },
        )

    initialize: Initialize = Field(
        title="Initialize",
        description="The raw recording, and what is kept of it.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: InfoBlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    dispatch: JobDispatch = Field(
        default=JobDispatch(),
        title="Job dispatch",
        description="How the recording is split into jobs, one per series, segment and probe.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    job_kwargs: JobKwargs = Field(
        default=JobKwargs(mp_context="spawn"),
        title="Job kwargs",
        description="SpikeInterface job kwargs.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    phase_shift: PhaseShift = Field(
        default_factory=PhaseShift,
        title="Phase shift",
        description="Corrects the sampling delay between channels (Neuropixels ADC multiplexing).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.PREPROCESSING,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    temporal_filter: TemporalFilterUnion = Field(
        default=HighpassFilterParams(),
        title="Filter",
        description="The frequency filter applied to the traces of each channel.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_UNION,
            SchemaKey.GROUP: BlockGroup.PREPROCESSING,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    detect_bad_channels: DetectBadChannels = Field(
        default_factory=DetectBadChannels,
        title="Detect bad channels",
        description="Detection of dead, noisy and outside channels.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.PREPROCESSING,
            SchemaKey.GROUP_ORDER: 2,
        },
    )
    denoising: DenoisingUnion = Field(
        default=CommonReference(),
        title="Denoising",
        description="How noise shared across channels is removed, once bad channels are gone.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_UNION,
            SchemaKey.GROUP: BlockGroup.PREPROCESSING,
            SchemaKey.GROUP_ORDER: 3,
        },
    )
    motion_correction: MotionCorrection = Field(
        default_factory=MotionCorrection,
        title="Motion correction",
        description="Estimation, and optionally correction, of the probe's motion.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.PREPROCESSING,
            SchemaKey.GROUP_ORDER: 4,
        },
    )

    @model_validator(mode="after")
    def one_input(self) -> Self:
        """Exactly one of the recording entity and the local NWB file is given."""
        if (self.initialize.recording is None) == (self.initialize.nwb_path is None):
            msg = "Give either a recording or an NWB file, not both or neither."
            raise ValueError(msg)
        return self

    def input_entities(self, db_client: entitysdk.client.Client) -> list[Entity]:
        """The recording entity, recorded as the input of the task config."""
        if self.initialize.recording is None:
            return []
        return [self.initialize.recording.entity(db_client=db_client)]


class AINDEPhysPreprocessingSingleConfig(AINDEPhysPreprocessingScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`AINDEPhysPreprocessingScanConfig`."""

    def preprocessing_pipeline(self, *, has_inter_sample_shift: bool) -> dict[str, dict]:
        """The ordered steps for ``spikeinterface.preprocessing.apply_preprocessing_pipeline``."""
        init = self.initialize
        steps: dict[str, dict] = {}
        if has_inter_sample_shift:
            steps["phase_shift"] = self.phase_shift.to_dict()
        steps[self.temporal_filter.pipeline_step] = self.temporal_filter.to_dict()
        steps["detect_and_remove_bad_channels"] = self.detect_bad_channels.to_dict(
            remove_out_channels=init.remove_out_channels,
            remove_bad_channels=init.remove_bad_channels,
        )
        steps[self.denoising.pipeline_step] = self.denoising.to_dict()
        return steps
