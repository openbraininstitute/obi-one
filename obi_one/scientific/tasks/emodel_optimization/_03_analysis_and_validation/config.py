"""ScanConfig and SingleConfig for the 02_analysis_and_validation stage."""

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
from obi_one.scientific.tasks.emodel_optimization._03_analysis_and_validation.blocks import (
    AnalysisInitialize,
    AnalysisSettings,
    CurrentscapeConfig,
)


class BlockGroup(StrEnum):
    """Block groups for the analysis stage."""

    SETUP = "Setup"
    ANALYSIS = "Analysis"


class EModelAnalysisAndValidationScanConfig(ScanConfig):
    """ScanConfig for ``--step=analyse`` from the L5PC example.

    The task seeds the working directory from the previous stage, merges the
    analysis-related ``pipeline_settings`` into ``recipes.json``, then runs
    ``pipeline.store_optimisation_results()``, ``pipeline.validation()`` and
    ``pipeline.plot(only_validated=...)``.
    """

    single_coord_class_name: ClassVar[str] = "EModelAnalysisAndValidationSingleConfig"
    name: ClassVar[str] = "EModel Analysis and Validation"
    description: ClassVar[str] = (
        "Run BluePyEModel analysis, validation, and plotting on optimisation results."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.ANALYSIS],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:  # noqa: ARG002, PLR6301
        return []

    initialize: AnalysisInitialize = Field(
        title="Initialize",
        description="Filesystem inputs and ``EModel_pipeline`` constructor arguments.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    analysis_settings: AnalysisSettings = Field(
        default_factory=AnalysisSettings,
        title="Analysis settings",
        description="Top-level ``pipeline_settings`` keys controlling analysis.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.ANALYSIS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    currentscape_config: CurrentscapeConfig = Field(
        default_factory=CurrentscapeConfig,
        title="Currentscape config",
        description="``currentscape_config`` (used when ``plot_currentscape=True``).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.ANALYSIS,
            SchemaKey.GROUP_ORDER: 1,
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


class EModelAnalysisAndValidationSingleConfig(
    EModelAnalysisAndValidationScanConfig, SingleConfigMixin
):
    """Single-coordinate variant of :class:`EModelAnalysisAndValidationScanConfig`."""

    def create_single_entity_with_config(  # noqa: PLR6301
        self,
        campaign: TaskConfig,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None
