"""Config of the spike sorting stage with Kilosort4."""

from typing import ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.aind_ephys._02_spikesorting.config import (
    AINDEPhysSpikeSortingScanConfig,
    AINDEPhysSpikeSortingSingleConfig,
    BlockGroup,
)
from obi_one.scientific.tasks.aind_ephys._02_spikesorting.kilosort4.blocks import (
    Kilosort4Clustering,
    Kilosort4DriftCorrection,
    Kilosort4Preprocessing,
    Kilosort4Runtime,
    Kilosort4SpikeDetection,
    Kilosort4Templates,
)


class AINDEPhysSpikeSortingKilosort4ScanConfig(AINDEPhysSpikeSortingScanConfig):
    """Sort the spikes of each preprocessed recording with Kilosort4, the AIND pipeline's default.

    Needs obi-one's ``kilosort`` extra, which launch jobs do not install yet. Also writes the
    sorter's motion estimate to ``spikesortedmotion_<name>/``.
    """

    name: ClassVar[str] = "AIND Ephys Spike Sorting with Kilosort4"
    description: ClassVar[str] = (
        "Sorts the spikes of preprocessed extracellular recordings with Kilosort4."
    )
    sorter_name: ClassVar[str] = "kilosort4"
    motion_correction_parameter: ClassVar[str] = "do_correction"

    preprocessing: Kilosort4Preprocessing = Field(
        default_factory=Kilosort4Preprocessing,
        title="Preprocessing",
        description="How Kilosort batches, filters, references and whitens the recording.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    drift_correction: Kilosort4DriftCorrection = Field(
        default_factory=Kilosort4DriftCorrection,
        title="Drift correction",
        description="Kilosort's own drift correction.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    spike_detection: Kilosort4SpikeDetection = Field(
        default_factory=Kilosort4SpikeDetection,
        title="Spike detection",
        description="Detection thresholds.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 2,
        },
    )
    templates: Kilosort4Templates = Field(
        default_factory=Kilosort4Templates,
        title="Templates",
        description="The shape and spatial grid of the templates.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 3,
        },
    )
    clustering: Kilosort4Clustering = Field(
        default_factory=Kilosort4Clustering,
        title="Clustering",
        description="Splitting and merging clusters, and which of them to keep.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 4,
        },
    )
    runtime: Kilosort4Runtime = Field(
        default=Kilosort4Runtime(),
        title="Runtime",
        description="Execution settings the platform defines.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )


class AINDEPhysSpikeSortingKilosort4SingleConfig(
    AINDEPhysSpikeSortingKilosort4ScanConfig, AINDEPhysSpikeSortingSingleConfig
):
    """Single-coordinate variant of :class:`AINDEPhysSpikeSortingKilosort4ScanConfig`."""
