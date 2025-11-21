from obi_one.core.block import Block
from obi_one.core.task import Task
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleCoordMixin
from pydantic import Discriminator
from pathlib import Path
from enum import StrEnum
from pydantic import Field, PositiveInt, PositiveFloat, NonNegativeInt, NonNegativeFloat
from typing import Annotated, ClassVar, Literal
import numpy as np

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
    description: ClassVar[str] = (
        "Spike sorting preprocessing configuration."
    )

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "block_block_group_order": [
                BlockGroup.SETUP,
                BlockGroup.PREPROCESSING,
                BlockGroup.SPIKE_SORTING,
            ],
        }


    setup_recording: SpikeSortingSetupRecording = Field(
        title="Recording setup",
        description="Recording setup.",
        group=BlockGroup.SETUP,
        group_order=0,
    )

    setup_advanced: SpikeSortingSetupAdvanced = Field(
        title="Advanced setup",
        description="Advanced setup.",
        group=BlockGroup.SETUP,
        group_order=1,
    )

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


class SpikeSortingTask(Task):
    """SpikeSortingPreprocessing."""

    title: ClassVar[str] = "Multi Electrode Recording Postprocessing"
    description: ClassVar[str] = (
        "Spike sorting preprocessing configuration."
    )

    single_config: SpikeSortingSingleConfig

    _pipeline_dict: dict = {}

    def _add_job_dispatch_dict(self):
        
        d = {}
        d["no-split-segments"] = not self.single_config.setup_advanced.split_segments
        d["no-split-groups"] = not self.single_config.setup.advanced.split_groups
        d["debug"] = not self.single_config.setup_recording.test_mode
        d["debug_duration"] = self.single_config.setup_recording.test_mode_duration
        d["skip_timestamps_check"] = self.single_config.setup_advanced.skip_timestamps_check
        d["multi_session_data"] = self.single_config.setup_advanced.multi_session_data
        d["min_recording_duration"] = self.single_config.setup_advanced.min_recording_duration
        d["input"] = "nwb" # Which 'loader' to use (aind | spikeglx | openephys | nwb | spikeinterface)

        spikeinterface_info = {}

        # REQUIRED e.g. 'plexon', 'neuralynx', 'intan' etc.
        spikeinterface_info["reader_type"] = "plexon"

        # OPTIONAL e.g. {'folder': '/path/to/folder'}
        spikeinterface_info["reader_kwargs"] = {}

        # OPTIONAL string or list of strings with the stream names to load (e.g. 'AP' or ['AP', 'LFP']).
        spikeinterface_info["keep_stream_substrings"] = "AP"

        # OPTIONAL string (or list of strings) with substrings used to skip streams (e.g. 'NIDQ' or ['USB', 'EVENTS']).
        spikeinterface_info["skip_stream_substrings"] = []

        # OPTIONAL: probe_paths (optional): string or dict the probe paths to a ProbeInterface JSON file (e.g. '/path/to/probe.json'). If a dict is provided, the key is the stream name and the value is the probe path. If reader_kwargs is not provided, the reader will be created with default parameters. The probe_path is required if the reader doesn't load the probe automatically.
        spikeinterface_info["probe_paths"] = None


        # WRITE spikeinterface_info to json

        # Add path to params
        d["spikeinterface_info"] = "PATH_TO_SPIKEINTERFACE_INFO_JSON"

        self._pipeline_dict["job_dispatch"] = d


    def _add_preprocessing_dict(self):
        d = {}

        d["job_kwargs"] = {
            "chunk_duration": "1s",
            "progress_bar": False,
            "mp_context": "spawn"
        }

        d["denoising_strategy"] = self.single_config.initialize.denoising_strategy
        d["min_preprocessing_duration"] = self.single_config.initialize.min_preprocessing

        if isinstance(d.frequency_filter, SpikeSortingPreprocessingHighPassFilter):
            d["highpass_filter"] = {
                "freq_min": self.single_config.frequency_filter.min_freq,
                "margin_ms": self.single_config.frequency_filter.margin,
            }
        elif isinstance(d.frequency_filter, SpikeSortingPreprocessingBandpassFilter):
            d["bandpass_filter"] = {
                "freq_min": self.single_config.frequency_filter.min_freq,
                "freq_max": self.single_config.frequency_filter.max_freq,
                "margin_ms": self.single_config.frequency_filter.margin,
            }

        d["phase_shift"] = {
            "margin_ms": self.single_config.initialize.phase_shift,
        }

        d["remove_out_channels"] = self.single_config.initialize.remove_out_channels
        d["remove_bad_channels"] = self.single_config.detect_bad_channels.remove_bad
        d["max_bad_channel_fraction"] = self.single_config.detect_bad_channels.max_bad_channel_fraction

        d["common_reference"] = {
            "reference": self.single_config.initialize.common_reference,
            "operator": self.single_config.initialize.common_reference_operator,
        }

        d["highpass_spatial_filter"] = {
            "n_channel_pad": self.single_config.high_pass_spatial_filter.n_channel_pad,
            "n_channel_taper": self.single_config.high_pass_spatial_filter.n_channel_taper,
            "direction": self.single_config.high_pass_spatial_filter.direction,
            "apply_agc": self.single_config.high_pass_spatial_filter.apply_agc,
            "agc_window_length_s": self.single_config.high_pass_spatial_filter.agc_window_length_s,
            "highpass_butter_order": self.single_config.high_pass_spatial_filter.highpass_butter_order,
            "highpass_butter_wn": self.single_config.high_pass_spatial_filter.highpass_butter_wn,
        }

        d["motion_correction"] = {
            "preset": self.single_config.motion_correction.preset,
            "detect_kwargs": self.single_config.motion_correction.detect_kwargs,
            "select_kwargs": self.single_config.motion_correction.select_kwargs,
            "localize_peaks_kwargs": self.single_config.motion_correction.localize_peaks_kwargs,
            "estimate_motion_kwargs": self.single_config.motion_correction.estimate_motion_kwargs,
            "interpolate_motion_kwargs": self.single_config.motion_correction.interpolate_motion_kwargs,
        }

        self._pipeline_dict["preprocessing"] = d


    def execute(self):
        self._add_job_dispatch_dict()
        self._add_preprocessing_dict()
        self._add_postprocessing_dict()