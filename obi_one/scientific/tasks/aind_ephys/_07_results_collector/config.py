"""ScanConfig for the aind-ephys-results-collector capsule."""

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from entitysdk import Client
from entitysdk.models import Entity, TaskConfig
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin


class BlockGroup(StrEnum):
    """Results-collector block groups."""

    SETUP = "Setup"


class AINDEPhysResultsCollectorScanConfig(ScanConfig):
    """ScanConfig wrapping the aind-ephys-results-collector CLI.

    The capsule aggregates dispatch + preprocessing + spikesort + postprocessing
    + curation + visualization outputs into a single directory layout
    (``preprocessed/``, ``spikesorted/``, ``postprocessed/``, ``curated/``,
    ``visualization/``) and emits the AIND-data-schema ``processing.json`` /
    ``data_description.json`` files.
    """

    single_coord_class_name: ClassVar[str] = "AINDEPhysResultsCollectorSingleConfig"
    name: ClassVar[str] = "AIND Ephys Results Collector"
    description: ClassVar[str] = (
        "Aggregate ephys-pipeline outputs into a single AIND-data-schema layout."
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
        """Top-level CLI / control parameters for the results-collector capsule."""

        dispatch_output_path: Path = Field(
            title="Dispatch output path",
            description="Directory containing ``job_*.json`` from the dispatch stage.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        preprocessing_output_path: Path = Field(
            title="Preprocessing output path",
            description="Directory containing the preprocessing capsule's results.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        spikesort_output_path: Path = Field(
            title="Spikesort output path",
            description="Directory containing ``spikesorted_<name>/`` folders.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        postprocessing_output_path: Path = Field(
            title="Postprocessing output path",
            description="Directory containing ``postprocessed_<name>.zarr`` folders.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        curation_output_path: Path = Field(
            title="Curation output path",
            description="Directory containing ``qc_*.npy`` and ``unit_classifier_*.csv``.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        visualization_output_path: Path = Field(
            title="Visualization output path",
            description="Directory containing the visualization capsule's outputs.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

        process_name: str = Field(
            default="sorted",
            title="Process name",
            description="Process name used in the derived data-description.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

        session_name: str = Field(
            default="ecephys_toy",
            title="Session name",
            description=(
                "Synthetic session name used for the ``ecephys_*`` folder the"
                " capsule expects in ``data/`` (must start with 'ecephys')."
            ),
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
        description="Top-level control parameters for the results-collector run.",
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


class AINDEPhysResultsCollectorSingleConfig(
    AINDEPhysResultsCollectorScanConfig, SingleConfigMixin
):
    """Single-coordinate variant of :class:`AINDEPhysResultsCollectorScanConfig`."""

    def create_single_entity_with_config(
        self,
        campaign: TaskConfig,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None

    def synthetic_data_description(self) -> dict:
        """Build a minimal ``data_description.json`` payload."""
        return {
            "name": self.initialize.session_name,
            "schema_version": "2.0.0",
            "creation_time": datetime.now(timezone.utc).isoformat(),
            "institution": {
                "name": "Allen Institute for Neural Dynamics",
                "abbreviation": "AIND",
            },
            "modalities": [
                {"name": "Extracellular electrophysiology", "abbreviation": "ecephys"}
            ],
            "subject_id": self.initialize.subject_id,
            "investigators": [{"name": "unknown"}],
            "funding_source": [
                {
                    "funder": {
                        "name": "Allen Institute for Neural Dynamics",
                        "abbreviation": "AIND",
                    }
                }
            ],
            "project_name": "toy_pipeline",
            "data_level": "raw",
            "tags": [],
        }
