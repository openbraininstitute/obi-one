"""ScanConfig and SingleConfig for the 02_emodel_optimization stage."""

import logging
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from entitysdk import Client
from entitysdk.models import Entity, TaskConfig
from entitysdk.types import (
    AssetLabel,
    ContentType,
    TaskActivityType,
    TaskConfigType,
)
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.library.info_scan_config.config import (
    BlockGroup as InfoBlockGroup,
    InfoScanConfig,
)
from obi_one.scientific.tasks.emodel_optimization.task2_emodel_optimization.blocks import (
    MorphologySelection,
    OptimizationInitialize,
    OptimizationParams,
    OptimizationSettings,
    ParametersSelection,
    ParamsFileSelection,
)

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block groups for the optimisation stage."""

    INPUT = "Input"
    MORPHOLOGY = "Morphology"
    PARAMETERS = "Parameters"
    OPTIMIZATION = "Optimization Settings"


class EModelOptimizationScanConfig(InfoScanConfig):
    """ScanConfig for the BluePyEModel optimisation step.

    Runs optimisation + analysis + export in a single task. Seeds the working
    directory from the extraction ``TaskResult`` assets, downloads morphology
    and ion channel model entities, merges optimisation settings into the
    recipe, and runs ``pipeline.optimise()`` followed by analysis and export.
    """

    single_coord_class_name: ClassVar[str] = "EModelOptimizationSingleConfig"
    name: ClassVar[str] = "EModel Optimization"
    description: ClassVar[str] = (
        "Run BluePyEModel parameter optimisation against extracted features,"
        " followed by analysis and draft emodel export."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            InfoBlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.INPUT,
            BlockGroup.MORPHOLOGY,
            BlockGroup.PARAMETERS,
            BlockGroup.OPTIMIZATION,
        ],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.emodel_optimization__campaign
    )
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.emodel_optimization__config_generation
    )

    def input_entities(self, db_client: Client) -> list[Entity]:
        entities: list[Entity] = [
            self.initialize.extraction_task_result.entity(db_client=db_client),
            self.morphology_selection.morphology.entity(db_client=db_client),
        ]
        entities.extend(
            icm.entity(db_client=db_client) for icm in self.parameters_selection.ion_channel_models
        )
        return entities

    @property
    def use_params_file(self) -> bool:
        """True if params-file mode is active (params_file_path is set)."""
        return bool(self.params_file.params_file_path)

    initialize: OptimizationInitialize = Field(
        title="Initialize",
        description="Entity-based inputs and ``EModel_pipeline`` constructor arguments.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.INPUT,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    morphology_selection: MorphologySelection = Field(
        title="Morphology",
        description="Morphology entity to stage into the working directory.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.MORPHOLOGY,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    parameters_selection: ParametersSelection = Field(
        default_factory=ParametersSelection,
        title="Parameters",
        description="Ion channel models for dynamic parameter building.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.PARAMETERS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    params_file: ParamsFileSelection = Field(
        default_factory=ParamsFileSelection,
        title="Params file (alternative)",
        description=(
            "Optional: provide a pre-built BluePyEModel params JSON file instead"
            " of using the dynamic builder. If set, this takes precedence over"
            " the ion channel models selection."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.PARAMETERS,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    optimization_settings: OptimizationSettings = Field(
        default_factory=OptimizationSettings,
        title="Optimization settings",
        description=(
            "Top-level ``pipeline_settings`` keys controlling optimisation, analysis, and export."
        ),
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

    @property
    def campaign_name(self) -> str:
        return self.info.campaign_name

    @property
    def campaign_description(self) -> str:
        return self.info.campaign_description

    def create_campaign_entity_with_config(  # ty:ignore[invalid-method-override]
        self,
        output_root: Path,  # noqa: ARG002
        multiple_value_parameters_dictionary: dict | None = None,  # noqa: ARG002
        db_client: Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> None:
        if db_client is None:
            return

        L.info("Registering emodel optimization campaign TaskConfig entity.")
        input_entities = self.input_entities(db_client)
        campaign = db_client.register_entity(
            TaskConfig(
                name=self.campaign_name,
                description=self.campaign_description,
                task_config_type=TaskConfigType.emodel_optimization__campaign,
                meta={},
                inputs=input_entities,
            )
        )
        self._campaign = campaign

        db_client.upload_content(
            entity_id=campaign.id,  # ty:ignore[invalid-argument-type]
            entity_type=TaskConfig,
            file_content=self.model_dump_json(indent=2).encode("utf-8"),
            file_name="scan_config.json",
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.task_config,
        )
        L.info("Campaign entity registered: %s", campaign.id)
        return

    def create_campaign_generation_entity(  # noqa: PLR6301
        self,
        generated: list,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None


class EModelOptimizationSingleConfig(EModelOptimizationScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`EModelOptimizationScanConfig`."""

    def create_single_entity_with_config(  # ty:ignore[invalid-method-override]
        self,
        campaign: TaskConfig,
        db_client: Client,
    ) -> None:
        if db_client is None:
            return

        L.info("Registering emodel optimization single TaskConfig entity.")
        input_entities = self.input_entities(db_client)
        single_config_entity = db_client.register_entity(
            TaskConfig(
                name=f"EModel Optimization Config {self.idx}",
                description=f"Single-coordinate config for emodel optimization (idx={self.idx}).",
                task_config_type=TaskConfigType.emodel_optimization__config,
                meta={},
                task_config_generator_id=campaign.id if campaign else None,
                inputs=input_entities,
            )
        )

        db_client.upload_content(
            entity_id=single_config_entity.id,  # ty:ignore[invalid-argument-type]
            entity_type=TaskConfig,
            file_content=self.model_dump_json(indent=2).encode("utf-8"),
            file_name="single_config.json",
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.task_config,
        )

        self.set_single_entity(single_config_entity)
        L.info("Single config entity registered: %s", single_config_entity.id)
        return
