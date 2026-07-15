"""ScanConfig and SingleConfig for the 01_efeature_extraction stage."""

import logging
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from entitysdk import Client
from entitysdk.models import Entity, TaskConfig
from entitysdk.types import AssetLabel, ContentType, TaskActivityType, TaskConfigType
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.library.info_scan_config.config import (
    BlockGroup as InfoBlockGroup,
    InfoScanConfig,
)
from obi_one.scientific.tasks.emodel_optimization.task1_efeature_extraction.blocks import (
    ExtractionInitialize,
    ProtocolAndFeatureSelection,
    Settings,
)

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block groups for the extraction stage."""

    INPUTS = "Inputs"
    PROTOCOLS_FEATURES = "Protocols & features"
    SETTINGS = "Settings"


class EModelEFeatureExtractionScanConfig(InfoScanConfig):
    """ScanConfig for the experimental e-feature extraction step.

    Runs BluePyEModel's ``extract_save_features_protocols`` on the experimental
    ephys traces and writes the resulting fitness-calculator configuration to
    ``./extracted_features.json``, ready to be picked up by the optimisation
    stage. No model assets are needed at this point.
    """

    single_coord_class_name: ClassVar[str] = "EModelEFeatureExtractionSingleConfig"
    name: ClassVar[str] = "EModel EFeature Extraction"
    description: ClassVar[str] = (
        "Extract experimental e-features from ephys traces via BluePyEModel."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            InfoBlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.INPUTS,
            BlockGroup.PROTOCOLS_FEATURES,
            BlockGroup.SETTINGS,
        ],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.efeature_extraction__campaign
    )
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.efeature_extraction__config_generation
    )

    def input_entities(self, db_client: Client) -> list[Entity]:
        return [r.entity(db_client=db_client) for r in self.initialize.electrical_cell_recording]

    initialize: ExtractionInitialize = Field(
        title="Inputs",
        description="Input recordings for feature extraction.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.INPUTS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    efeatures_by_protocol: ProtocolAndFeatureSelection = Field(
        default_factory=ProtocolAndFeatureSelection,
        title="Protocols & features",
        description=(
            "Per-protocol timing, amplitudes and e-feature selection. The"
            " frontend renders a ``select_efeatures_by_protocol`` picker,"
            " restricted to the protocols returned by"
            " ``/declared/electrical-cell-recording-protocols`` for the chosen"
            " recordings."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.PROTOCOLS_FEATURES,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    settings: Settings = Field(
        default_factory=Settings,
        title="Settings",
        description="Global extraction-flow parameters and amplitude mode.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETTINGS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    def create_campaign_entity_with_config(  # ty:ignore[invalid-method-override]
        self,
        output_root: Path,  # noqa: ARG002
        multiple_value_parameters_dictionary: dict | None = None,  # noqa: ARG002
        db_client: Client = None,  # ty:ignore[invalid-parameter-default]
    ) -> None:
        if db_client is None:
            return

        L.info("Registering efeature extraction campaign TaskConfig entity.")
        input_entities = self.input_entities(db_client)
        campaign = db_client.register_entity(
            TaskConfig(
                name=self.campaign_name,
                description=self.campaign_description,
                task_config_type=TaskConfigType.efeature_extraction__campaign,
                meta={},
                inputs=input_entities,
            )
        )
        self._campaign = campaign

        # Upload the scan config as an asset on the campaign entity.
        db_client.upload_content(
            entity_id=campaign.id,  # ty:ignore[invalid-argument-type]
            entity_type=TaskConfig,
            file_content=self.model_dump_json(indent=2).encode("utf-8"),
            file_name="scan_config.json",
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.task_config,
        )
        L.info("Campaign entity registered: %s", campaign.id)
        return campaign

    def create_campaign_generation_entity(  # noqa: PLR6301
        self,
        generated: list,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None


class EModelEFeatureExtractionSingleConfig(EModelEFeatureExtractionScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`EModelEFeatureExtractionScanConfig`."""

    def create_single_entity_with_config(  # ty:ignore[invalid-method-override]
        self,
        campaign: TaskConfig,
        db_client: Client,
    ) -> None:
        if db_client is None:
            return

        L.info("Registering efeature extraction single TaskConfig entity.")
        input_entities = self.input_entities(db_client)
        single_config_entity = db_client.register_entity(
            TaskConfig(
                name=f"EFeature Extraction Config {self.idx}",
                description=f"Single-coordinate config for efeature extraction (idx={self.idx}).",
                task_config_type=TaskConfigType.efeature_extraction__config,
                meta={},
                task_config_generator_id=campaign.id if campaign else None,
                inputs=input_entities,
            )
        )

        # Upload the single config JSON as an asset.
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
