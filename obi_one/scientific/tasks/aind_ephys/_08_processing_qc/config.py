"""ScanConfig for the aind-ephys-processing-qc capsule."""

from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from entitysdk import Client
from entitysdk.models import Entity, TaskConfig
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field, NonNegativeFloat

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.units import Units


class BlockGroup(StrEnum):
    """Processing-QC block groups."""

    SETUP = "Setup"


class AINDEPhysProcessingQCScanConfig(ScanConfig):
    """ScanConfig wrapping the aind-ephys-processing-qc CLI.

    The capsule expects the aggregated layout produced by the
    results-collector stage (``preprocessed/``, ``postprocessed/`` etc.)
    plus the dispatch ``job_*.json`` and an ``ecephys_*`` session folder.
    It writes per-recording figures + a ``QualityControl`` aind-data-schema
    document to ``../results/``.
    """

    single_coord_class_name: ClassVar[str] = "AINDEPhysProcessingQCSingleConfig"
    name: ClassVar[str] = "AIND Ephys Processing QC"
    description: ClassVar[str] = (
        "Run the aind-ephys-processing-qc capsule on the collected ephys-pipeline outputs."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:  # noqa: ARG002, PLR6301
        return []

    class Initialize(Block):
        """Top-level CLI / control parameters for the processing-QC capsule."""

        collected_output_path: Path = Field(
            title="Collected output path",
            description=(
                "Directory containing the results-collector layout"
                " (``preprocessed/``, ``spikesorted/``, ``postprocessed/`` etc.)."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        dispatch_output_path: Path = Field(
            title="Dispatch output path",
            description="Directory containing ``job_*.json`` from the dispatch stage.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

        compute_event_metrics: bool = Field(
            default=False,
            title="Compute event metrics",
            description=(
                "Compute event-driven metrics from HARP. The toy data has no"
                " HARP files so this defaults to False (passes"
                " --no-event-metrics)."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )
        min_duration_allow_failed: NonNegativeFloat = Field(
            default=0.0,
            title="Min duration to allow failed",
            description=(
                "Recordings shorter than this duration may fail without"
                " breaking the run."
            ),
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.SECONDS,
            },
        )

        session_name: str = Field(
            default="ecephys_toy",
            title="Session name",
            description="Synthetic ``ecephys_*`` folder name (must start with 'ecephys').",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        subject_id: str = Field(
            default="000000",
            title="Subject id",
            description="Subject id written into the synthetic ``subject.json``.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

    initialize: Initialize = Field(
        title="Initialize",
        description="Top-level control parameters for the processing-QC run.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
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


class AINDEPhysProcessingQCSingleConfig(
    AINDEPhysProcessingQCScanConfig, SingleConfigMixin
):
    """Single-coordinate variant of :class:`AINDEPhysProcessingQCScanConfig`."""

    def create_single_entity_with_config(
        self,
        campaign: TaskConfig,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None
