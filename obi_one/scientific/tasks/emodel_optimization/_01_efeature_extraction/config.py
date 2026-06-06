"""ScanConfig and SingleConfig for the 01_efeature_extraction stage."""

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
    ExtractionInitialize,
    ProtocolAndFeatureSelection,
    Settings,
)


class BlockGroup(StrEnum):
    """Block groups for the extraction stage."""

    SETUP = "Setup"
    EXTRACTION = "Extraction"
    TARGETS = "Targets"


class EModelEFeatureExtractionScanConfig(ScanConfig):
    """ScanConfig for the experimental e-feature extraction step.

    Runs ``bluepyefe.extract.extract_efeatures`` on the experimental ephys
    traces and writes the resulting fitness-calculator configuration to
    ``./extracted_features.json``, ready to be picked up by the optimisation
    stage. No model assets are needed at this point.
    """

    single_coord_class_name: ClassVar[str] = "EModelEFeatureExtractionSingleConfig"
    name: ClassVar[str] = "EModel EFeature Extraction"
    description: ClassVar[str] = "Extract experimental e-features from ephys traces via bluepyefe."

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.EXTRACTION, BlockGroup.TARGETS],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:
        return [r.entity(db_client=db_client) for r in self.initialize.electrical_cell_recording]

    initialize: ExtractionInitialize = Field(
        title="Initialize",
        description="Filesystem inputs for feature extraction.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    settings: Settings = Field(
        default_factory=Settings,
        title="Settings",
        description="Combined eFEL and ``bluepyefe.extract`` parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTRACTION,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    efeatures_by_protocol: ProtocolAndFeatureSelection = Field(
        default_factory=ProtocolAndFeatureSelection,
        title="EFeatures by protocol",
        description=(
            "Per-protocol timing, amplitudes and e-feature selection. The"
            " frontend renders a ``select_efeatures_by_protocol`` picker,"
            " restricted to the protocols returned by"
            " ``/declared/electrical-cell-recording-protocols`` for the chosen"
            " recordings."
        ),
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
