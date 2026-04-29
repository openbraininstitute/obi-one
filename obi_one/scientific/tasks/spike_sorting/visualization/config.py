"""ScanConfig for the aind-ephys-visualization capsule."""

from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal

from entitysdk import Client
from entitysdk.models import Entity, TaskConfig
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.tasks.spike_sorting.visualization.blocks import (
    DriftViz,
    MotionViz,
    TimeseriesViz,
    VisualizationJobKwargs,
)


class BlockGroup(StrEnum):
    """Visualization block groups."""

    SETUP = "Setup"
    FIGURES = "Figures"


class AINDEPhysVisualizationScanConfig(ScanConfig):
    """ScanConfig wrapping the aind-ephys-visualization CLI.

    The capsule expects ``../data/`` to contain the union of dispatch +
    preprocessing + postprocessing + curation outputs. Without a
    ``KACHERY_API_KEY`` environment variable it skips kachery uploads and
    only emits local PNGs/PDFs.
    """

    single_coord_class_name: ClassVar[str] = "AINDEPhysVisualizationSingleConfig"
    name: ClassVar[str] = "AIND Ephys Visualization"
    description: ClassVar[str] = (
        "Run the aind-ephys-visualization capsule on the ephys-pipeline outputs."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.FIGURES],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:  # noqa: ARG002, PLR6301
        return []

    class Initialize(Block):
        """Top-level CLI / control parameters for the visualization capsule."""

        dispatch_output_path: Path = Field(
            title="Dispatch output path",
            description="Directory containing ``job_*.json`` from the dispatch stage.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        preprocessing_output_path: Path = Field(
            title="Preprocessing output path",
            description=(
                "Directory containing ``preprocessed_<name>/``,"
                " ``binary_<name>.json`` and ``preprocessedviz_<name>.json``."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        postprocessing_output_path: Path = Field(
            title="Postprocessing output path",
            description="Directory containing ``postprocessed_<name>.zarr``.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        curation_output_path: Path = Field(
            title="Curation output path",
            description=(
                "Directory containing ``qc_<name>.npy`` and"
                " ``unit_classifier_<name>.csv``."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

        output_format: Literal["png", "pdf"] = Field(
            default="png",
            title="Output format",
            description="Format used for matplotlib figures.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
        )
        n_jobs: int = Field(
            default=1,
            title="n_jobs",
            description="Parallel job count (-1 for all cores).",
            json_schema_extra={SchemaKey.UI_HIDDEN: True},
        )

    initialize: Initialize = Field(
        title="Initialize",
        description="Top-level control parameters for the visualization run.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    job_kwargs: VisualizationJobKwargs = Field(
        default_factory=VisualizationJobKwargs,
        title="Job kwargs",
        description="SpikeInterface job_kwargs.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    timeseries: TimeseriesViz = Field(
        default_factory=TimeseriesViz,
        title="Timeseries",
        description="Timeseries-figure parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.FIGURES,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    drift: DriftViz = Field(
        default_factory=DriftViz,
        title="Drift",
        description="Drift-map figure parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.FIGURES,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    motion: MotionViz = Field(
        default_factory=MotionViz,
        title="Motion",
        description="Motion-figure parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.FIGURES,
            SchemaKey.GROUP_ORDER: 2,
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


class AINDEPhysVisualizationSingleConfig(
    AINDEPhysVisualizationScanConfig, SingleConfigMixin
):
    """Single-coordinate variant of :class:`AINDEPhysVisualizationScanConfig`."""

    def create_single_entity_with_config(
        self,
        campaign: TaskConfig,  # noqa: ARG002
        db_client: Client,  # noqa: ARG002
    ) -> None:
        return None

    def params_dict(self) -> dict:
        """Build the params.json payload the capsule expects."""
        return {
            "job_kwargs": self.job_kwargs.to_dict(),
            "timeseries": self.timeseries.to_dict(),
            "drift": self.drift.to_dict(),
            "motion": self.motion.to_dict(),
        }
