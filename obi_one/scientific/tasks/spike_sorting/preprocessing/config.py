from enum import StrEnum
from typing import ClassVar

from pydantic import Field

from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleCoordMixin
from obi_one.scientific.tasks.spike_sorting.preprocessing.blocks import (
    SpikeSortingPreprocessingDetectBadChannels,
    SpikeSortingPreprocessingFilterUnion,
    SpikeSortingPreprocessingHighPassSpatialFilter,
    SpikeSortingPreprocessingInitialize,
    SpikeSortingPreprocessingMotionCorrection,
)

# Job Dispatch
# https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch/

# Preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing/blob/main/code/params.json


class BlockGroup(StrEnum):
    """SpikeSorting Block Group."""

    SETUP = "Setup"
    PREPROCESSING = "Preprocessing"
    SPIKE_SORTING = "Spike sorting"


class SpikeSortingScanConfig(ScanConfig):
    single_coord_class_title: ClassVar[str] = "SpikeSortingPreprocessingSingleConfig"
    title: ClassVar[str] = "Multi Electrode Recording Postprocessing"
    description: ClassVar[str] = "Spike sorting preprocessing configuration."

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "block_block_group_order": [
                BlockGroup.SETUP,
                BlockGroup.PREPROCESSING,
                BlockGroup.SPIKE_SORTING,
            ],
        }

    preprocessing_initialize: SpikeSortingPreprocessingInitialize = Field(
        title="Preprocessing initialization",
        description="Preprocessing initialization.",
        group=BlockGroup.PREPROCESSING,
        group_order=0,
    )
    frequency_filter: SpikeSortingPreprocessingFilterUnion = Field(
        title="Frequency filter",
        description="Frequency filter.",
        group=BlockGroup.PREPROCESSING,
        group_order=1,
    )
    spatial_filter: SpikeSortingPreprocessingHighPassSpatialFilter = Field(
        title="Spatial filter",
        description="Spatial filter.",
        group=BlockGroup.PREPROCESSING,
        group_order=2,
    )
    detect_bad_channels: SpikeSortingPreprocessingDetectBadChannels = Field(
        title="Bad channel detection",
        description="Bad channel detection.",
        group=BlockGroup.PREPROCESSING,
        group_order=2,
    )
    motion_correction: SpikeSortingPreprocessingMotionCorrection = Field(
        title="Motion correction",
        description="Motion correction.",
        group=BlockGroup.PREPROCESSING,
        group_order=3,
    )


class SpikeSortingSingleConfig(SpikeSortingScanConfig, SingleCoordMixin):
    """SpikeSortingPreprocessingSingleConfig."""

    def dictionary_representation(self) -> dict:
        d = {}
        d.update(self.preprocessing_initialize.dictionary_representation())
        d.update(self.frequency_filter.dictionary_representation())
        d.update(self.spatial_filter.dictionary_representation())
        d.update(self.detect_bad_channels.dictionary_representation())
        d.update(self.motion_correction.dictionary_representation())
        return d
