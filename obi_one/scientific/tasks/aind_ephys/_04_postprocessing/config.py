"""Config for the postprocessing stage of the AIND ephys pipeline."""

from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.tasks.aind_ephys._04_postprocessing.blocks import (
    Correlograms,
    IsiHistograms,
    NoiseLevels,
    PrincipalComponents,
    QualityMetrics,
    RandomSpikes,
    Sparsity,
    SpikeLocations,
    TemplateMetrics,
    TemplateSimilarity,
    UnitLocations,
    Waveforms,
)
from obi_one.scientific.tasks.aind_ephys.blocks import JobKwargs


class BlockGroup(StrEnum):
    """Postprocessing block groups."""

    SETUP = "Setup"
    EXTENSIONS = "Extensions"
    METRICS = "Metrics"


def block_field(block: type[Block], title: str, description: str, group: str, order: int) -> Any:
    """A grouped field holding a block, defaulting to the block's defaults."""
    return Field(
        default_factory=block,
        title=title,
        description=description,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: group,
            SchemaKey.GROUP_ORDER: order,
        },
    )


class AINDEPhysPostprocessingScanConfig(ScanConfig):
    """Remove duplicated units, then compute waveforms, locations and quality metrics.

    Port of https://github.com/AllenNeuralDynamics/aind-ephys-postprocessing. Writes each
    recording's ``SortingAnalyzer`` to ``postprocessed_<name>.zarr``.
    """

    name: ClassVar[str] = "AIND Ephys Postprocessing"
    description: ClassVar[str] = "Computes waveforms and quality metrics of sorted units."

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.EXTENSIONS, BlockGroup.METRICS],
    }

    class Initialize(Block):
        preprocessing_output_path: Path = Field(
            title="Preprocessing output",
            description="Folder of the preprocessing stage's output.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        spikesort_output_path: Path = Field(
            title="Spike sorting output",
            description="Folder of the spike sorting stage's output.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
        )
        use_motion_corrected: bool = Field(
            default=False,
            title="Use motion-corrected traces",
            description="Whether waveforms come from the motion-corrected traces.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )
        duplicate_threshold: float | None = Field(
            default=0.9,
            title="Duplicate threshold",
            description="Spike agreement above which one of two units is removed. None keeps all.",
            json_schema_extra={SchemaKey.UI_HIDDEN: True},
        )
        return_in_uV: bool = Field(  # ruff: ignore[mixed-case-variable-in-class-scope]
            default=True,
            title="Return in microvolts",
            description="Whether waveforms and templates are scaled to microvolts.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )

    initialize: Initialize = Field(
        title="Initialize",
        description="The preprocessed recordings and their sortings.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    job_kwargs: JobKwargs = block_field(
        JobKwargs, "Job kwargs", "SpikeInterface job kwargs.", BlockGroup.SETUP, 1
    )
    sparsity: Sparsity = block_field(
        Sparsity, "Sparsity", "Channels kept for each unit.", BlockGroup.SETUP, 2
    )
    random_spikes: RandomSpikes = block_field(
        RandomSpikes, "Random spikes", "Spikes sampled per unit.", BlockGroup.EXTENSIONS, 0
    )
    noise_levels: NoiseLevels = block_field(
        NoiseLevels, "Noise levels", "Noise level estimation.", BlockGroup.EXTENSIONS, 1
    )
    waveforms: Waveforms = block_field(
        Waveforms, "Waveforms", "Waveform extraction window.", BlockGroup.EXTENSIONS, 2
    )
    template_similarity: TemplateSimilarity = block_field(
        TemplateSimilarity,
        "Template similarity",
        "Similarity of templates.",
        BlockGroup.EXTENSIONS,
        3,
    )
    correlograms: Correlograms = block_field(
        Correlograms, "Correlograms", "Spike train correlograms.", BlockGroup.EXTENSIONS, 4
    )
    isi_histograms: IsiHistograms = block_field(
        IsiHistograms,
        "ISI histograms",
        "Inter-spike interval histograms.",
        BlockGroup.EXTENSIONS,
        5,
    )
    unit_locations: UnitLocations = block_field(
        UnitLocations, "Unit locations", "Localization of units.", BlockGroup.EXTENSIONS, 6
    )
    spike_locations: SpikeLocations = block_field(
        SpikeLocations, "Spike locations", "Localization of spikes.", BlockGroup.EXTENSIONS, 7
    )
    template_metrics: TemplateMetrics = block_field(
        TemplateMetrics, "Template metrics", "Metrics of the templates.", BlockGroup.METRICS, 0
    )
    principal_components: PrincipalComponents = block_field(
        PrincipalComponents, "Principal components", "PCA of waveforms.", BlockGroup.METRICS, 1
    )
    quality_metrics: QualityMetrics = block_field(
        QualityMetrics, "Quality metrics", "Unit quality metrics.", BlockGroup.METRICS, 2
    )


class AINDEPhysPostprocessingSingleConfig(AINDEPhysPostprocessingScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`AINDEPhysPostprocessingScanConfig`."""

    def extensions(self) -> dict[str, dict]:
        """The extensions to compute, in order, before the quality metrics."""
        return {
            "random_spikes": self.random_spikes.to_dict(),
            "noise_levels": self.noise_levels.to_dict(),
            "waveforms": self.waveforms.to_dict(),
            "templates": {},
            "spike_amplitudes": {},
            "template_similarity": self.template_similarity.to_dict(),
            "correlograms": self.correlograms.to_dict(),
            "isi_histograms": self.isi_histograms.to_dict(),
            "unit_locations": self.unit_locations.to_dict(),
            "spike_locations": self.spike_locations.to_dict(),
            "template_metrics": self.template_metrics.to_dict(),
            "principal_components": self.principal_components.to_dict(),
            "amplitude_scalings": {},
            "valid_unit_periods": {},
        }
