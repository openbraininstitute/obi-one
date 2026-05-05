"""ScanConfig and SingleConfig for the 03_export_final_model stage."""

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
from obi_one.scientific.tasks.emodel_optimization._04_export_final_model.blocks import (
    ExportInitialize,
    ExportSettings,
)


class BlockGroup(StrEnum):
    """Block groups for the export stage."""

    SETUP = "Setup"
    EXPORT = "Export"


class EModelExportFinalModelScanConfig(ScanConfig):
    """ScanConfig for ``--step=export_hoc`` / ``--step=export_sonata``.

    The task seeds the working directory from the analysis stage's output and
    runs ``export_emodels_hoc`` and/or ``export_emodels_sonata`` based on the
    block flags. Outputs land at ``./export_emodels_hoc/`` and
    ``./export_emodels_sonata/`` inside ``coordinate_output_root``.
    """

    single_coord_class_name: ClassVar[str] = "EModelExportFinalModelSingleConfig"
    name: ClassVar[str] = "EModel Export Final Model"
    description: ClassVar[str] = "Export the optimised BluePyEModel models to HOC and/or SONATA."

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.EXPORT],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:  # noqa: ARG002, PLR6301
        return []

    initialize: ExportInitialize = Field(
        title="Initialize",
        description="Filesystem inputs and ``EModel_pipeline`` constructor arguments.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    export_settings: ExportSettings = Field(
        default_factory=ExportSettings,
        title="Export settings",
        description="Flags for ``export_emodels_hoc`` and ``export_emodels_sonata``.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXPORT,
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


class EModelExportFinalModelSingleConfig(EModelExportFinalModelScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`EModelExportFinalModelScanConfig`."""

    def create_single_entity_with_config(  # noqa: PLR6301
        self,
        campaign: TaskConfig,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None
