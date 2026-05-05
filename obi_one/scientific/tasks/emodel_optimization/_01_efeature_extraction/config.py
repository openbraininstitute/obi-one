"""ScanConfig and SingleConfig for the 00_efeature_extraction stage."""

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
from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.blocks import (
    EFELSettings,
    ExtractionInitialize,
    ExtractionSettings,
    ExtractionTargets,
)


class BlockGroup(StrEnum):
    """Block groups for the extraction stage."""

    SETUP = "Setup"
    EXTRACTION = "Extraction"
    TARGETS = "Targets"


class EModelEFeatureExtractionScanConfig(ScanConfig):
    """ScanConfig for the BluePyEModel feature-extraction step.

    Mirrors ``python pipeline.py --step=extract --emodel=<EMODEL>`` from the
    BluePyEModel L5PC example: the task copies the user-provided ephys data,
    morphologies, mechanisms, params and recipes into the coord output, runs
    ``configure_targets()`` followed by ``pipeline.extract_efeatures()``, and
    leaves a self-contained working directory ready for the optimisation stage.
    """

    single_coord_class_name: ClassVar[str] = "EModelEFeatureExtractionSingleConfig"
    name: ClassVar[str] = "EModel EFeature Extraction"
    description: ClassVar[str] = "Run BluePyEModel feature extraction on experimental ephys traces."

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.EXTRACTION, BlockGroup.TARGETS],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:  # noqa: ARG002, PLR6301
        return []

    initialize: ExtractionInitialize = Field(
        title="Initialize",
        description="Filesystem inputs and ``EModel_pipeline`` constructor arguments.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    extraction_settings: ExtractionSettings = Field(
        default_factory=ExtractionSettings,
        title="Extraction settings",
        description="Top-level ``pipeline_settings`` keys controlling extraction.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTRACTION,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    efel_settings: EFELSettings = Field(
        default_factory=EFELSettings,
        title="eFEL settings",
        description="``efel_settings`` block (threshold, interp_step, strict_stiminterval).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTRACTION,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    targets: ExtractionTargets = Field(
        default_factory=ExtractionTargets,
        title="Extraction targets",
        description="Targets, protocols and ecodes metadata that drive ``configure_targets()``.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.TARGETS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    def create_campaign_entity_with_config(  # noqa: PLR6301
        self,
        output_root: Path,  # noqa: ARG002
        multiple_value_parameters_dictionary: dict | None = None,  # noqa: ARG002
        db_client: Client = None,  # noqa: ARG002
    ) -> None:
        return None

    def create_campaign_generation_entity(  # noqa: PLR6301
        self,
        generated: list,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None


class EModelEFeatureExtractionSingleConfig(EModelEFeatureExtractionScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`EModelEFeatureExtractionScanConfig`."""

    def create_single_entity_with_config(  # noqa: PLR6301
        self,
        campaign: TaskConfig,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None
