"""Config of the spike sorting stage with Lupin."""

from typing import ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.aind_ephys._02_spikesorting.config import (
    AINDEPhysSpikeSortingScanConfig,
    AINDEPhysSpikeSortingSingleConfig,
    BlockGroup,
)
from obi_one.scientific.tasks.aind_ephys._02_spikesorting.lupin.blocks import (
    LupinClustering,
    LupinMotionCorrection,
    LupinPreprocessing,
    LupinSpikeDetection,
    LupinTemplateMatching,
)


class AINDEPhysSpikeSortingLupinScanConfig(AINDEPhysSpikeSortingScanConfig):
    """Sort the spikes of each preprocessed recording with Lupin.

    Needs torch, which launch jobs do not install yet.
    """

    name: ClassVar[str] = "AIND Ephys Spike Sorting with Lupin"
    description: ClassVar[str] = (
        "Sorts the spikes of preprocessed extracellular recordings with Lupin."
    )
    sorter_name: ClassVar[str] = "lupin"
    motion_correction_parameter: ClassVar[str] = "apply_motion_correction"

    preprocessing: LupinPreprocessing = Field(
        default_factory=LupinPreprocessing,
        title="Preprocessing",
        description=("Whether and how the sorter filters, references and whitens the recording."),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    motion_correction: LupinMotionCorrection = Field(
        default_factory=LupinMotionCorrection,
        title="Motion correction",
        description="The sorter's own motion correction.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    spike_detection: LupinSpikeDetection = Field(
        default_factory=LupinSpikeDetection,
        title="Spike detection",
        description="Peak detection.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 2,
        },
    )
    clustering: LupinClustering = Field(
        default_factory=LupinClustering,
        title="Clustering",
        description="Grouping peaks into units.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 3,
        },
    )
    template_matching: LupinTemplateMatching = Field(
        default_factory=LupinTemplateMatching,
        title="Template matching",
        description="The templates, and matching them to the recording.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 4,
        },
    )


class AINDEPhysSpikeSortingLupinSingleConfig(
    AINDEPhysSpikeSortingLupinScanConfig, AINDEPhysSpikeSortingSingleConfig
):
    """Single-coordinate variant of :class:`AINDEPhysSpikeSortingLupinScanConfig`."""
