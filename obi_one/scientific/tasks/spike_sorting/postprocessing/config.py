"""ScanConfig for the aind-ephys-postprocessing capsule."""

from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from entitysdk import Client
from entitysdk.models import Entity, TaskConfig
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.tasks.spike_sorting.postprocessing.blocks import (
    Correlograms,
    IsiHistograms,
    NoiseLevels,
    PostprocessingJobKwargs,
    PrincipalComponents,
    QualityMetrics,
    RandomSpikes,
    Sparsity,
    SpikeAmplitudes,
    SpikeLocations,
    TemplateMetrics,
    TemplateSimilarity,
    UnitLocations,
    Waveforms,
)


class BlockGroup(StrEnum):
    """Postprocessing block groups."""

    SETUP = "Setup"
    EXTENSIONS = "Extensions"
    QUALITY = "Quality metrics"


class AINDEPhysPostprocessingScanConfig(ScanConfig):
    """ScanConfig wrapping the aind-ephys-postprocessing CLI.

    The capsule consumes ``preprocessed_<name>/`` + ``binary_<name>.json`` from
    the preprocessing stage **and** ``spikesorted_<name>/`` from the sorting
    stage; both must be present in ``../data/``. It writes one
    ``postprocessed_<name>.zarr`` per recording to ``../results/``.
    """

    single_coord_class_name: ClassVar[str] = "AINDEPhysPostprocessingSingleConfig"
    name: ClassVar[str] = "AIND Ephys Postprocessing"
    description: ClassVar[str] = (
        "Run the aind-ephys-postprocessing capsule on preprocessed + sorted ephys data."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP,
            BlockGroup.EXTENSIONS,
            BlockGroup.QUALITY,
        ],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = None
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = None

    def input_entities(self, db_client: Client) -> list[Entity]:  # noqa: ARG002, PLR6301
        return []

    class Initialize(Block):
        """Top-level CLI / control parameters for the postprocessing capsule."""

        preprocessing_output_path: Path = Field(
            title="Preprocessing output path",
            description=(
                "Directory containing ``preprocessed_<name>/`` directories and"
                " matching ``binary_<name>.json`` files (output of"
                " AINDEPhysPreprocessingTask)."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        spikesort_output_path: Path = Field(
            title="Spikesort output path",
            description=(
                "Directory containing ``spikesorted_<name>/`` directories"
                " (output of AINDEPhysSpikesortKilosort4Task)."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )

        use_motion_corrected: bool = Field(
            default=False,
            title="Use motion-corrected recording",
            description="Pass --use-motion-corrected to the capsule.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )
        duplicate_threshold: PositiveFloat | list[PositiveFloat] = Field(
            default=0.9,
            title="Duplicate threshold",
            description="Cosine-similarity threshold for unit de-duplication.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
        )
        return_scaled: bool = Field(
            default=True,
            title="Return scaled",
            description="Whether to return waveforms in physical units (μV).",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )
        n_jobs: int = Field(
            default=1,
            title="n_jobs",
            description="Parallel job count (-1 for all cores).",
            json_schema_extra={SchemaKey.UI_HIDDEN: True},
        )

    initialize: Initialize = Field(
        title="Initialize",
        description="Top-level control parameters for the postprocessing run.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    job_kwargs: PostprocessingJobKwargs = Field(
        default_factory=PostprocessingJobKwargs,
        title="Job kwargs",
        description="SpikeInterface job_kwargs.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    sparsity: Sparsity = Field(
        default_factory=Sparsity,
        title="Sparsity",
        description="Sparsity-mask parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTENSIONS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    random_spikes: RandomSpikes = Field(
        default_factory=RandomSpikes,
        title="Random spikes",
        description="Spike-selection parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTENSIONS,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    noise_levels: NoiseLevels = Field(
        default_factory=NoiseLevels,
        title="Noise levels",
        description="Noise-level estimation parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTENSIONS,
            SchemaKey.GROUP_ORDER: 2,
        },
    )

    waveforms: Waveforms = Field(
        default_factory=Waveforms,
        title="Waveforms",
        description="Waveform-extraction parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTENSIONS,
            SchemaKey.GROUP_ORDER: 3,
        },
    )

    spike_amplitudes: SpikeAmplitudes = Field(
        default_factory=SpikeAmplitudes,
        title="Spike amplitudes",
        description="Spike-amplitude parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTENSIONS,
            SchemaKey.GROUP_ORDER: 4,
        },
    )

    template_similarity: TemplateSimilarity = Field(
        default_factory=TemplateSimilarity,
        title="Template similarity",
        description="Template-similarity parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTENSIONS,
            SchemaKey.GROUP_ORDER: 5,
        },
    )

    correlograms: Correlograms = Field(
        default_factory=Correlograms,
        title="Correlograms",
        description="Correlogram parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTENSIONS,
            SchemaKey.GROUP_ORDER: 6,
        },
    )

    isi_histograms: IsiHistograms = Field(
        default_factory=IsiHistograms,
        title="ISI histograms",
        description="ISI-histogram parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTENSIONS,
            SchemaKey.GROUP_ORDER: 7,
        },
    )

    unit_locations: UnitLocations = Field(
        default_factory=UnitLocations,
        title="Unit locations",
        description="Unit-localization parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTENSIONS,
            SchemaKey.GROUP_ORDER: 8,
        },
    )

    spike_locations: SpikeLocations = Field(
        default_factory=SpikeLocations,
        title="Spike locations",
        description="Spike-localization parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTENSIONS,
            SchemaKey.GROUP_ORDER: 9,
        },
    )

    template_metrics: TemplateMetrics = Field(
        default_factory=TemplateMetrics,
        title="Template metrics",
        description="Template-metrics parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTENSIONS,
            SchemaKey.GROUP_ORDER: 10,
        },
    )

    principal_components: PrincipalComponents = Field(
        default_factory=PrincipalComponents,
        title="Principal components",
        description="PCA parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTENSIONS,
            SchemaKey.GROUP_ORDER: 11,
        },
    )

    quality_metrics: QualityMetrics = Field(
        default_factory=QualityMetrics,
        title="Quality metrics",
        description="Quality-metrics parameters.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.QUALITY,
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


class AINDEPhysPostprocessingSingleConfig(
    AINDEPhysPostprocessingScanConfig, SingleConfigMixin
):
    """Single-coordinate variant of :class:`AINDEPhysPostprocessingScanConfig`."""

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
            "sparsity": self.sparsity.to_dict(),
            "duplicate_threshold": self.initialize.duplicate_threshold,
            "return_scaled": self.initialize.return_scaled,
            "random_spikes": self.random_spikes.to_dict(),
            "noise_levels": self.noise_levels.to_dict(),
            "waveforms": self.waveforms.to_dict(),
            "templates": {},
            "spike_amplitudes": self.spike_amplitudes.to_dict(),
            "template_similarity": self.template_similarity.to_dict(),
            "correlograms": self.correlograms.to_dict(),
            "isi_histograms": self.isi_histograms.to_dict(),
            "unit_locations": self.unit_locations.to_dict(),
            "spike_locations": self.spike_locations.to_dict(),
            "template_metrics": self.template_metrics.to_dict(),
            "principal_components": self.principal_components.to_dict(),
            "quality_metrics_names": list(self.quality_metrics.metric_names),
            "quality_metrics": self.quality_metrics.to_dict(),
        }
