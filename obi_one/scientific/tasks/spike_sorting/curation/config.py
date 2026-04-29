"""ScanConfig for the aind-ephys-curation capsule."""

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
from obi_one.scientific.tasks.spike_sorting.curation.blocks import CurationJobKwargs


class BlockGroup(StrEnum):
    """Curation block groups."""

    SETUP = "Setup"
    CURATION = "Curation"


class AINDEPhysCurationScanConfig(ScanConfig):
    """ScanConfig wrapping the aind-ephys-curation CLI.

    The capsule consumes ``postprocessed_<name>.zarr`` folders from the
    postprocessing stage. For each, it applies a default-QC pandas query on
    the analyzer's quality_metrics (writing ``qc_<name>.npy``) and runs two
    HuggingFace classifiers (writing ``unit_classifier_<name>.csv``).
    """

    single_coord_class_name: ClassVar[str] = "AINDEPhysCurationSingleConfig"
    name: ClassVar[str] = "AIND Ephys Curation"
    description: ClassVar[str] = (
        "Run the aind-ephys-curation capsule (default QC + UnitRefine classifiers)."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.CURATION],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:  # noqa: ARG002, PLR6301
        return []

    class Initialize(Block):
        """Top-level CLI / control parameters for the curation capsule."""

        postprocessing_output_path: Path = Field(
            title="Postprocessing output path",
            description=(
                "Directory containing one or more ``postprocessed_<name>.zarr``"
                " folders (output of AINDEPhysPostprocessingTask)."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

        query: str = Field(
            default=(
                "isi_violations_ratio < 0.5 and presence_ratio > 0.8"
                " and amplitude_cutoff < 0.1"
            ),
            title="QC query",
            description=(
                "Pandas-query string applied to the analyzer's quality_metrics"
                " dataframe to flag units as passing/failing default QC."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

        noise_neural_classifier: str = Field(
            default="SpikeInterface/UnitRefine_noise_neural_classifier",
            title="Noise/neural classifier",
            description="HuggingFace repo id of the noise-vs-neural classifier.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        sua_mua_classifier: str = Field(
            default="SpikeInterface/UnitRefine_sua_mua_classifier",
            title="SUA/MUA classifier",
            description="HuggingFace repo id of the SUA-vs-MUA classifier.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

        n_jobs: int = Field(
            default=1,
            title="n_jobs",
            description="Parallel job count (-1 for all cores).",
            json_schema_extra={SchemaKey.UI_HIDDEN: True},
        )

    initialize: Initialize = Field(
        title="Initialize",
        description="Top-level control parameters for the curation run.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    job_kwargs: CurationJobKwargs = Field(
        default_factory=CurationJobKwargs,
        title="Job kwargs",
        description="SpikeInterface job_kwargs.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
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


class AINDEPhysCurationSingleConfig(AINDEPhysCurationScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`AINDEPhysCurationScanConfig`."""

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
            "query": self.initialize.query,
            "noise_neural_classifier": self.initialize.noise_neural_classifier,
            "sua_mua_classifier": self.initialize.sua_mua_classifier,
        }
