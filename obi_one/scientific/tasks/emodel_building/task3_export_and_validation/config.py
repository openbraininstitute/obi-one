"""ScanConfig and SingleConfig for the 03_export_and_validation stage."""

import logging
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from entitysdk import Client
from entitysdk.models import TaskConfig
from entitysdk.types import (
    AssetLabel,
    ContentType,
    TaskActivityType,
    TaskConfigType,
)
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.tasks.emodel_building.task3_export_and_validation.blocks import (
    ExportAndValidationInitialize,
)

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block groups for the export + validation stage."""

    SETUP = "Setup"


class EModelExportAndValidationScanConfig(InfoScanConfig):
    """ScanConfig for the export + validation stage.

    Validates the draft EModel/MEModel from the optimisation stage and
    promotes them to active lifecycle status. All validation and plotting
    settings are read from the optimisation recipe (stored on the TaskResult).
    """

    single_coord_class_name: ClassVar[str] = "EModelExportAndValidationSingleConfig"
    name: ClassVar[str] = "EModel Export and Validation"
    description: ClassVar[str] = (
        "Validate the draft EModel/MEModel and promote to active lifecycle."
        " Settings come from the optimisation recipe."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.optimized_emodel_analysis_validation__campaign
    )
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.optimized_emodel_analysis_validation__config_generation
    )

    def input_entities(self, db_client: Client) -> list:
        return [
            self.initialize.optimization_task_result.entity(db_client=db_client),
            self.initialize.memodel.entity(db_client=db_client),
        ]

    initialize: ExportAndValidationInitialize = Field(
        title="Initialize",
        description="Entity-based inputs for the export + validation stage.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
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

        L.info("Registering export+validation campaign TaskConfig entity.")
        input_entities = self.input_entities(db_client)
        campaign = db_client.register_entity(
            TaskConfig(
                name=self.campaign_name,
                description=self.campaign_description,
                task_config_type=TaskConfigType.optimized_emodel_analysis_validation__campaign,
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


class EModelExportAndValidationSingleConfig(EModelExportAndValidationScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`EModelExportAndValidationScanConfig`."""

    def create_single_entity_with_config(  # ty:ignore[invalid-method-override]
        self,
        campaign: TaskConfig,
        db_client: Client,
    ) -> None:
        if db_client is None:
            return

        L.info("Registering export+validation single TaskConfig entity.")
        input_entities = self.input_entities(db_client)
        single_config_entity = db_client.register_entity(
            TaskConfig(
                name=f"EModel Export+Validation Config {self.idx}",
                description=f"Single-coordinate config for export+validation (idx={self.idx}).",
                task_config_type=TaskConfigType.optimized_emodel_analysis_validation__config,
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
