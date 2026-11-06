"""ScanConfig and SingleConfig for the 03_emodel_validation stage."""

from enum import StrEnum
from typing import ClassVar

from entitysdk import Client
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.library.info_scan_config.config import (
    BlockGroup as InfoBlockGroup,
    InfoScanConfig,
)
from obi_one.scientific.tasks.emodel_building.task3_emodel_validation.blocks import (
    EModelInput,
    ValidationSettings,
    ValidationTargetEFeaturesInput,
)


class BlockGroup(StrEnum):
    """Block groups for the validation stage."""

    INPUTS = "Inputs"
    SETTINGS = "Settings"


class EModelValidationScanConfig(InfoScanConfig):
    """ScanConfig for BluePyEModel score validation of an optimised e-model.

    Rebuilds the BluePyEModel working directory of the optimisation that produced the
    EModel, on its exemplar morphology, with the selected target e-features (the
    optimisation targets or another extraction), and scores the optimised parameters.
    Validation on other morphologies belongs to ME-model validation, where the
    e-model/morphology pair is an MEModel entity.
    """

    single_coord_class_name: ClassVar[str] = "EModelValidationSingleConfig"
    name: ClassVar[str] = "EModel Validation"
    description: ClassVar[str] = (
        "Score an optimised e-model against held-out or freshly extracted e-features"
        " with BluePyEModel."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            InfoBlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.INPUTS,
            BlockGroup.SETTINGS,
        ],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.optimized_emodel_analysis_validation__campaign
    )
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.optimized_emodel_analysis_validation__config_generation
    )

    emodel: EModelInput = Field(
        title="E-model",
        description="Optimised e-model to validate.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.INPUTS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    target_efeatures: ValidationTargetEFeaturesInput = Field(
        title="Target e-features",
        description=(
            "E-features the e-model is scored against: the e-model's optimisation targets "
            "or another e-feature extraction."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.INPUTS,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    settings: ValidationSettings = Field(
        default_factory=ValidationSettings,
        title="Validation settings",
        description="Validation protocols, score aggregation and threshold.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETTINGS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    def input_entities(self, db_client: Client) -> list:
        return [
            self.emodel.emodel.entity(db_client=db_client),
            self.target_efeatures.task_result.entity(db_client=db_client),
        ]

    @property
    def campaign_name(self) -> str:
        return self.info.campaign_name

    @property
    def campaign_description(self) -> str:
        return self.info.campaign_description


class EModelValidationSingleConfig(EModelValidationScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`EModelValidationScanConfig`."""
