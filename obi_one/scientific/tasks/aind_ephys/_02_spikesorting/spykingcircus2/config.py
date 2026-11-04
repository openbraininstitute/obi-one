"""Config of the spike sorting stage with SpykingCircus2."""

from typing import ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.tasks.aind_ephys._02_spikesorting.config import (
    AINDEPhysSpikeSortingScanConfig,
    AINDEPhysSpikeSortingSingleConfig,
    BlockGroup,
)
from obi_one.scientific.tasks.aind_ephys._02_spikesorting.spykingcircus2.blocks import (
    CircusOmpMatching,
    SpykingCircus2Clustering,
    SpykingCircus2MatchingUnion,
    SpykingCircus2MotionCorrection,
    SpykingCircus2PeakSelection,
    SpykingCircus2Preprocessing,
    SpykingCircus2SpikeDetection,
    SpykingCircus2Templates,
)


class AINDEPhysSpikeSortingSpykingCircus2ScanConfig(AINDEPhysSpikeSortingScanConfig):
    """Sort the spikes of each preprocessed recording with SpykingCircus2."""

    name: ClassVar[str] = "AIND Ephys Spike Sorting with SpykingCircus2"
    description: ClassVar[str] = (
        "Sorts the spikes of preprocessed extracellular recordings with SpykingCircus2."
    )
    sorter_name: ClassVar[str] = "spykingcircus2"
    motion_correction_parameter: ClassVar[str] = "apply_motion_correction"

    preprocessing: SpykingCircus2Preprocessing = Field(
        default_factory=SpykingCircus2Preprocessing,
        title="Preprocessing",
        description=("Whether and how the sorter filters, references and whitens the recording."),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    motion_correction: SpykingCircus2MotionCorrection = Field(
        default_factory=SpykingCircus2MotionCorrection,
        title="Motion correction",
        description="The sorter's own motion correction.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    spike_detection: SpykingCircus2SpikeDetection = Field(
        default_factory=SpykingCircus2SpikeDetection,
        title="Spike detection",
        description="Peak detection, and the channels used around each spike.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 2,
        },
    )
    peak_selection: SpykingCircus2PeakSelection = Field(
        default_factory=SpykingCircus2PeakSelection,
        title="Peak selection",
        description="How many detected peaks go on to clustering.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 3,
        },
    )
    clustering: SpykingCircus2Clustering = Field(
        default_factory=SpykingCircus2Clustering,
        title="Clustering",
        description="Grouping the selected peaks into units.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 4,
        },
    )
    templates: SpykingCircus2Templates = Field(
        default_factory=SpykingCircus2Templates,
        title="Templates",
        description="The templates' shape, and which of them are kept.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 5,
        },
    )
    matching: SpykingCircus2MatchingUnion = Field(
        default=CircusOmpMatching(),
        title="Template matching",
        description="Finding every spike of every unit by template matching.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_UNION,
            SchemaKey.GROUP: BlockGroup.SORTING,
            SchemaKey.GROUP_ORDER: 6,
        },
    )


class AINDEPhysSpikeSortingSpykingCircus2SingleConfig(
    AINDEPhysSpikeSortingSpykingCircus2ScanConfig, AINDEPhysSpikeSortingSingleConfig
):
    """Single-coordinate variant of :class:`AINDEPhysSpikeSortingSpykingCircus2ScanConfig`."""
