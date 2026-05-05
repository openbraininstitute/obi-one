"""ScanConfig and SingleConfig for the 01_emodel_optimization stage."""

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
from obi_one.scientific.tasks.emodel_optimization._02_emodel_optimization.blocks import (
    OptimizationInitialize,
    OptimizationParams,
    OptimizationSettings,
)


class BlockGroup(StrEnum):
    """Block groups for the optimisation stage."""

    SETUP = "Setup"
    OPTIMIZATION = "Optimization"


class EModelOptimizationScanConfig(ScanConfig):
    """ScanConfig for the BluePyEModel optimisation step.

    Mirrors ``python pipeline.py --step=optimise --emodel=<EMODEL>`` from the
    L5PC example. The task seeds its working directory from the previous
    stage's output, merges the optimisation-related ``pipeline_settings``
    overrides into ``recipes.json``, and runs ``pipeline.optimise(seed=...)``.
    """

    single_coord_class_name: ClassVar[str] = "EModelOptimizationSingleConfig"
    name: ClassVar[str] = "EModel Optimization"
    description: ClassVar[str] = (
        "Run BluePyEModel parameter optimisation against extracted features."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.OPTIMIZATION],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:  # noqa: ARG002, PLR6301
        return []

    initialize: OptimizationInitialize = Field(
        title="Initialize",
        description="Filesystem inputs and ``EModel_pipeline`` constructor arguments.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    optimization_settings: OptimizationSettings = Field(
        default_factory=OptimizationSettings,
        title="Optimization settings",
        description="Top-level ``pipeline_settings`` keys controlling optimisation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.OPTIMIZATION,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    optimization_params: OptimizationParams = Field(
        default_factory=OptimizationParams,
        title="Optimization params",
        description="``optimisation_params`` (offspring size).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.OPTIMIZATION,
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


class EModelOptimizationSingleConfig(EModelOptimizationScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`EModelOptimizationScanConfig`."""

    def create_single_entity_with_config(  # noqa: PLR6301
        self,
        campaign: TaskConfig,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None
