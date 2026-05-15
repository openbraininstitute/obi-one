import json
import shlex
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from entitysdk import Client
from entitysdk.models import Entity, TaskConfig
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field

from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.tasks.aind_ephys._01_dispatch.blocks import (
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
    """ScanConfig wrapping the aind-ephys-job-dispatch CLI."""

    single_coord_class_name: ClassVar[str] = "AINDEPhysDispatchSingleConfig"
    name: ClassVar[str] = "Multi Electrode Recording Postprocessing"
    description: ClassVar[str] = "Spike sorting preprocessing configuration."

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP,
            BlockGroup.PREPROCESSING,
            BlockGroup.SPIKE_SORTING,
        ],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:  # noqa: ARG002, PLR6301
        return []

    dispatch_basic: DispatchBasic = Field(
        title="Recording setup",
        description="Top-level dispatch flags applied to every recording.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    dispatch_data_dependent: DispatchDataDependent = Field(
        title="Data dependent options",
        description="Input-format-dependent dispatch options.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    dispatch_debug: DispatchDebug = Field(
        title="Debug setup",
        description="Debug-mode dispatch options.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 2,
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


class AINDEPhysDispatchSingleConfig(AINDEPhysDispatchScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`AINDEPhysDispatchScanConfig`."""

    def create_single_entity_with_config(
        self,
        campaign: TaskConfig,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None

    def command_line_representation(self) -> str:
        """Build the dispatch CLI invocation for this single coordinate.

        See https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch/blob/main/code/run_capsule.py
        for the meaning of each flag.
        """
        parts: list[str] = ["python", "-u", "code/run_capsule.py"]

        parts += ["--input", self.dispatch_data_dependent.input_format]

        if not self.dispatch_basic.split_segments:
            parts.append("--no-split-segments")
        if not self.dispatch_basic.split_groups:
            parts.append("--no-split-groups")
        if self.dispatch_basic.skip_timestamps_check:
            parts.append("--skip-timestamps-check")
        parts += ["--min-recording-duration", str(self.dispatch_basic.min_recording_duration)]

        if self.dispatch_debug.debug_mode:
            parts.append("--debug")
            parts += ["--debug-duration", str(self.dispatch_debug.debug_duration)]

        if self.dispatch_data_dependent.multi_session_data:
            parts.append("--multi-session")

        if self.dispatch_data_dependent.input_format == "spikeinterface":
            info = self.dispatch_data_dependent.spikeinterface_info
            if info is None:
                msg = "spikeinterface_info is required when input_format == 'spikeinterface'."
                raise ValueError(msg)
            parts += ["--spikeinterface-info", json.dumps(info.to_dict())]

        if (
            self.dispatch_data_dependent.input_format == "nwb"
            and self.dispatch_data_dependent.nwb_files is not None
        ):
            parts += ["--nwb-files", self.dispatch_data_dependent.nwb_files]

        return shlex.join(parts)
