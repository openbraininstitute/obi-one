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



class SpikeSortingSetupRecording(Block):
    """SpikeSortingSetupRecording."""

    recording: Path | list[Path] = Field(
        default=Path(""),
        title="Recording path",
        description="Path to the recording file.",
    )

    test_mode: bool | list[bool] = Field(
        default=False,
        title="Test mode",
        description="Whether to run in test mode.",
    )

    test_mode_duration: PositiveFloat | list[PositiveFloat] = Field(
        default=60.0,
        title="Test mode duration",
        description="Duration for test mode in seconds.",
        unit="s"
    )

class SpikeSortingSetupAdvanced(Block):
    """SpikeSortingSetupAdvanced."""

    split_segments: bool | list[bool] = Field(
        default=False,
        title="Split segments",
        description="Whether to split segments in the recording.",
    )

    split_groups: bool | list[bool] = Field(
        default=False,
        title="Split groups",
        description="Whether to split groups in the recording.",
    )

    skip_timestamps_check: bool | list[bool] = Field(
        default=False,
        title="Skip timestamps check",
        description="Whether to skip timestamps check.",
    )

    multi_session_data: bool | list[bool] = Field(
        default=False,
        title="Multi-session data",
        description="Whether the data is multi-session.",
    )

class SpikeSortingPreprocessingHighPassFilter(Block):
    min_freq: PositiveFloat | list[PositiveFloat] = Field(
        default=300.0,
        title="Minimum frequency (Hz)",
        description="Minimum frequency for high-pass filter in Hz.",
        unit="Hz"
    )

    margin: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=300.0,
        title="Margin (ms)",
        description="Margin for high-pass filter in milliseconds.",
        unit="ms"
    )

class SpikeSortingPreprocessingBandpassFilter(SpikeSortingPreprocessingHighPassFilter):
    max_freq: PositiveFloat | list[PositiveFloat] = Field(
        default=300.0,
        title="Minimum frequency (Hz)",
        description="Minimum frequency for high-pass filter in Hz.",
        unit="Hz"
    )

    # MAKE SURE max > min freq with validator

SpikeSortingPreprocessingFilterUnion = Annotated[
    SpikeSortingPreprocessingHighPassFilter
    | SpikeSortingPreprocessingBandpassFilter,
    Discriminator("type"),
]

class SpikeSortingPreprocessingInitialize(Block):

    denoising_strategy: Literal['cmr'] | list[Literal['cmr']] = Field(
        default='cmr',
        title="Denoising strategy",
        description="Denoising strategy to apply to the data.",
    )

    min_preprocessing_duration: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=120.0,
        title="Minimum preprocessing duration (s)",
        description="Minimum duration for preprocessing in seconds.",
        unit="s"
    )

    phase_shift: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        title="Phase shift (ms)",
        description="Phase shift to apply to the data in seconds.",
        unit="ms"
    )

    remove_out_channels: bool | list[bool] = Field(
        default=True,
        title="Remove out channels",
        description="Whether to remove out channels from the data.",
    )

    common_reference: Literal['global'] | list[Literal['global']] = Field(
        default='global',
        title="Common reference",
        description="Common reference strategy to apply to the data.",
    )

    common_reference_operator: Literal['median'] | list[Literal['median']] = Field(
        default='median',
        title="Common reference operator",
        description="Operator to use for common reference.",
    )




class SpikeSortingPreprocessingHighPassSpatialFilter(Block):

    n_channel_pad: int | list[int] = Field(
        default=60,
        title="Number of channels to pad",
        description="Number of channels to pad for high-pass spatial filtering.",
    )

    n_channel_taper: int | list[int] | None = Field(
        default=None,
        title="Number of channels to taper",
        description="Number of channels to taper for high-pass spatial filtering.",
    )

    direction: Literal['x', 'y'] = Field(
        default='y',
        title="Filter direction",
        description="Direction of the high-pass spatial filter.",
    )

    apply_agc: bool | list[bool] = Field(
        default=True,
        title="Apply high-pass spatial filter",
        description="Whether to apply high-pass spatial filter.",
    )

    agc_window_length_s: PositiveFloat | list[PositiveFloat] = Field(
        default=0.5,
        title="AGC window length (s)",
        description="Window length for automatic gain control (AGC) in seconds.",
    )

    highpass_butter_order: int | list[int] = Field(
        default=3,
        title="High-pass Butterworth filter order",
        description="Order of the high-pass Butterworth filter.",
    )

    highpass_butter_wn: float | list[float] = Field(
        default=0.01,
        title="High-pass Butterworth filter cutoff frequency (Hz)",
        description="Cutoff frequency for the high-pass Butterworth filter in Hz.",
    )


class SpikeSortingPreprocessingDetectBadChannels(Block):

    # REMOVAL PARAMETERS
    remove_bad_channels: bool | list[bool] = Field(
        default=True,
        title="Remove bad channels",
        description="Whether to remove bad channels from the data.",
    )
    
    max_bad_channel_fraction: float | list[float] = Field(
        default=0.5,
        title="Maximum bad channel fraction",
        description="Maximum fraction of bad channels allowed.",
    )

    # DETECTION PARAMETERS
    method: Literal["coherence+psd"] | list[Literal["coherence+psd"]] = Field(
        default="coherence+psd",
        title="Method",
        description="Method for detecting bad channels.",
    )

    dead_channel_threshold: float | list[float] = Field(
        default=-0.5,
        title="Dead channel threshold",
        description="Threshold for detecting dead channels.",
    )

    noisy_channel_threshold: float | list[float] = Field(
        default=1.0,
        title="Noisy channel threshold",
        description="Threshold for detecting noisy channels.",
    )

    outside_channel_threshold: float | list[float] = Field(
        default=-0.3,
        title="Outside channel threshold",
        description="Threshold for detecting outside channels.",
    )

    outside_channels_location: Literal["top"] = Field(
        default="top",
        title="Outside channels location",
        description="Location of outside channels.",
    )

    n_neighbours: NonNegativeInt | list[NonNegativeInt] = Field(
        default=11,
        title="Number of neighbours",
        description="Number of neighbouring channels to consider.",
    )

    seed: int | list[int] = Field(
        default=1
        title="Random seed",
        description="Random seed for reproducibility.",
    )

class SpikeSortingPreprocessingMotionCorrection(Block):

    preset: Literal['dredge_fast'] | list[Literal['dredge_fast']] = Field(
        default='dredge_fast',
        title="Motion correction preset",
        description="Preset for motion correction.",
    )

    detect_kwargs: dict | list[dict] = Field(
        default={},
        title="Detection kwargs",
        description="Keyword arguments for motion detection.",
    )

    select_kwargs: dict | list[dict] = Field(
        default={},
        title="Selection kwargs",
        description="Keyword arguments for motion selection.",
    )

    localize_peaks_kwargs: dict | list[dict] = Field(
        default={},
        title="Localize peaks kwargs",
        description="Keyword arguments for peak localization.",
    )

    estimate_motion_kwargs: dict | list[dict] = Field(
        default={"win_step_norm": 0.1, "win_scale_norm": 0.1},
        title="Estimate motion kwargs",
        description="Keyword arguments for motion estimation.",
    )

    interpolate_motion_kwargs: dict | list[dict] = Field(
        default={},
        title="Interpolate motion kwargs",
        description="Keyword arguments for motion interpolation.",
    )


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


class Kilosort4BasicSetup(Block):

    sampling_frequency: float | list[float] = Field(
        default=True,
        title="Sampling frequency",
        description="Sampling frequency of probe.",
    )

    batch_size: int | list[int] = Field(
        default=60000,
        title="Batch size",
        description="This sets the number of samples included in each batch of data to be sorted,\
            with a default of 60000 corresponding to 2 seconds for a sampling rate of 30000. For \
            probes with fewer channels (say, 64 or less), increasing batch_size to include more \
            data may improve results because it allows for better drift estimation (more spikes to \
            estimate drift from).",
    )

    nblocks: int | list[int] = Field(
        default=1,
        title="Number of blocks",
        description="This is the number of sections the probe is divided into when performing \
            drift correction. The default of nblocks = 1 indicates rigid registration (the \
            same amount of drift is applied to the entire probe). If you see different amounts \
            of drift in your data depending on depth along the probe, increasing nblocks will \
            help get a better drift estimate. nblocks=5 can be a good choice for single-shank \
            Neuropixels probes. For probes with fewer channels (around 64 or less) or with \
            sparser spacing (around 50um or more between contacts), drift estimates are not \
            likely to be accurate, so drift correction should be skipped by setting nblocks = 0",
    )

    th_universal: float | list[float] = Field(
        default=10.0,
        title="Universal threshold",
        description="These control the threshold for spike detection when applying the \
            universal and learned templates, respectively (loosely similar to Th(1) and \
            Th(2) in previous versions). If few spikes are detected, or if you see neurons \
            disappearing and reappearing over time when viewing results in Phy, it may help \
            to decrease Th_learned. To detect more units overall, it may help to reduce \
            Th_universal. Try reducing each threshold by 1 or 2 at a time..",
    )

    th_learned: float | list[float] = Field(
        default=8,
        title="Learned threshold",
        description="These control the threshold for spike detection when applying the \
            universal and learned templates, respectively (loosely similar to Th(1) and \
            Th(2) in previous versions). If few spikes are detected, or if you see neurons \
            disappearing and reappearing over time when viewing results in Phy, it may help \
            to decrease Th_learned. To detect more units overall, it may help to reduce \
            Th_universal. Try reducing each threshold by 1 or 2 at a time..",
    )

    # tmin: float | list[float] = Field(
    #     default=-0.0015,
    #     title="tmin",
    #     description="Time in seconds when data used for sorting should begin.",
    # )

    # tmax: float | list[float] = Field(
    #     default=np.inf,
    #     title="tmax",
    #     description="Time in seconds when data used for sorting should end. By default,\
    #                     ends at the end of the recording.",
    # )

class Kilosort4AdvancedSetup(Block):

    nt: PositiveInt | list[PositiveInt] = Field( # Would be nice in milliseconds?
        title="Spike waveform width",
        description="Spike waveform width.",
        unit="Timesteps"
    )

    dmin: PositiveFloat | list[PositiveFloat] | None = Field(
        default=None,
        title="Vertical spacing - Universal templates",
        description="These adjust the vertical spacing, of the \
            universal templates used during spike detection, as well as the vertical and \
            lateral sizes of channel neighborhoods used for clustering. By default, Kilosort \
            will attempt to determine a good value for dmin based on the median distance between \
            contacts, which tends to work well for Neuropixels-like probes. However, if contacts \
            are irregularly spaced, you may need to specify this manually. The default for dminx \
            is 32um, which is also well suited to Neuropixels probes. For other probes, try setting \
            dminx to the median lateral distance between contacts as a starting point. Note that as\
            of version 4.0.11, the kcoords variable in the probe layout will be used to restrict \
            template placement within each shank. Each shank should have a unique kcoords value that \
            is the same for all contacts on that shank."
        unit="um"
    )

    dminx: PositiveFloat | list[PositiveFloat] = Field(
        default=32.0
        title="Horizontal spacing - Universal templates"
        description="Adjusts the lateral spacing of the \
            universal templates used during spike detection, as well as the lateral sizes of \
            channel neighborhoods used for clustering. By default, Kilosort will attempt to \
            determine a good value for dmin based on the median distance between \
            contacts, which tends to work well for Neuropixels-like probes. However, if contacts \
            are irregularly spaced, you may need to specify this manually. The default for dminx \
            is 32um, which is also well suited to Neuropixels probes. For other probes, try setting \
            dminx to the median lateral distance between contacts as a starting point. Note that as\
            of version 4.0.11, the kcoords variable in the probe layout will be used to restrict \
            template placement within each shank. Each shank should have a unique kcoords value that \
            is the same for all contacts on that shank."
        unit="um"
    )

    min_template_size: PositiveFloat | list[PositiveFloat] = Field(
        default=10,
        title="Minimum template size",
        description="This sets the standard deviation of the smallest Gaussian spatial envelope " \
            "used to generate universal templates, with a default of 10 microns. You may need " \
            "to increase this for probes with wider spaces between contacts.",
        unit="um"
    )

    nearest_chans: PositiveInt | list[PositiveInt] = Field(
        default=10,
        title="N nearest channels",
        description="This is the number of nearest channels and template locations, " \
            "respectively, used when assigning templates to spikes during spike " \
            "detection. nearest_chans cannot be larger than the total number of channels " \
            "on the probe, so it will need to be reduced for probes with less than 10 channels. " \
            "nearest_templates does not have this restriction. However, for probes with around " \
            "64 channels or less and sparsely spaced contacts, decreasing nearest_templates " \
            "to be less than or equal to the number of channels helps avoid numerical instability."
    )

    nearest_templates: PositiveInt | list[PositiveInt] = Field(
        default=100,
        title="N nearest templates",
        description="This is the number of nearest channels and template locations, " \
            "respectively, used when assigning templates to spikes during spike " \
            "detection. nearest_chans cannot be larger than the total number of channels " \
            "on the probe, so it will need to be reduced for probes with less than 10 channels. " \
            "nearest_templates does not have this restriction. However, for probes with around " \
            "64 channels or less and sparsely spaced contacts, decreasing nearest_templates " \
            "to be less than or equal to the number of channels helps avoid numerical instability."
    )

    x_centers: PositiveInt | list[PositiveInt] | None = Field(
        default=None,
        title="X Centres",
        description="The number of x-positions to use when determining centers for template " \
            "groupings. Specifically, this is the number of centroids to look for when " \
            "using k-means to cluster the x-positions for the probe. In most cases you should " \
            "not need to specify this. However, for probes with contacts arranged in a " \
            "2D grid, we recommend setting x_centers such that centers are placed every " \
            "200-300um so that there are not too many templates in each group. For example, " \
            "for an array that is 2000um in width, try x_centers = 10. If contacts are very " \
            "densely spaced, you may need to use a higher value for better performance."
    )

    duplicate_spike_ms: PositiveFloat | list[PositiveFloat] = Field(
        default=0.25,
        title="Duplicate spike window",
        description="After sorting has finished, spikes that occur within this many ms of each \
            other, from the same unit, are assumed to be artifacts and removed. If you see \
            otherwise good neurons with large peaks around 0ms when viewing correlograms in \
            Phy, increasing this value can help remove those artifacts. Warning!!! Do not \
            increase this value beyond 0.5ms as it will interfere with the ACG and CCG \
            refractory period estimations (which normally ignores the central 1ms of the \
            correlogram)."
        unit="ms"
    )


# https://kilosort.readthedocs.io/en/latest/parameters.html
class KS4SpikeSortingScanConfig(SpikeSortingScanConfig):
    """Kilosort4SpikeSortingScanConfig."""

    single_coord_class_title: ClassVar[str] = "Kilosort4SpikeSortingSingleConfig"
    title: ClassVar[str] = "Kilosort4 Spike Sorting"
    description: ClassVar[str] = (
        "Kilosort4 spike sorting configuration."
    )

    
    kilosort4_basic_setup: Kilosort4BasicSetup = Field(
        title="Kilosort 4 Basic",
        description="Kilosort 4 Basic Setup.",
        group=BlockGroup.SPIKE_SORTING,
        group_order=0,
    )

    kilosort4_advanced_setup: Kilosort4AdvancedSetup = Field(
        title="Kilosort 4 Advanced",
        description="Kilosort 4 Advanced Setup.",
        group=BlockGroup.SPIKE_SORTING,
        group_order=1,
    )

    



class KS4SpikeSortingSingleConfig(SpikeSortingSingleConfig):
    """Kilosort4SpikeSortingSingleConfig."""

class KS4SpikeSortingTask(Task):

    single_config: KS4SpikeSortingSingleConfig

    def execute(self):
        super().execute()

        self._pipeline_dict["kilosort4"] = {
            # "job_kwargs": {
            #     "chunk_duration": "1s",
            #     "progress_bar": False
            # },
            "skip_motion_correction": False,
            "min_drift_channels": 96,
            "raise_if_fails": True,
            "clear_cache": False,
            "sorter": {
                "batch_size": self.single_config.kilosort4_basic_setup.batch_size,
                "nblocks": self.single_config.kilosort4_basic_setup.nblocks,
                "Th_universal": self.single_config.kilosort4_basic_setup.th_universal,
                "Th_learned": self.single_config.kilosort4_basic_setup.th_learned,

                "nt": self.single_config.kilosort4_advanced_setup.nt,
                "dmin": self.single_config.kilosort4_advanced_setup.dmin,
                "dminx": self.single_config.kilosort4_advanced_setup.dminx,
                "min_template_size": self.single_config.kilosort4_advanced_setup.min_template_size,
                "nearest_chans": self.single_config.kilosort4_advanced_setup.nearest_chans,
                "nearest_templates": self.single_config.kilosort4_advanced_setup.nearest_templates,
                "x_centers": self.single_config.kilosort4_advanced_setup.x_centers,
                "duplicate_spike_ms": self.single_config.kilosort4_advanced_setup.duplicate_spike_ms,

                "do_CAR": True,
                "invert_sign": False,
                "shift": None,
                "scale": None,
                "artifact_threshold": None,
                "nskip": 25,
                "whitening_range": 32,
                "highpass_cutoff": 300,
                "binning_depth": 5,
                "sig_interp": 20,
                "drift_smoothing": [0.5, 0.5, 0.5],
                "nt0min": None,
                "template_sizes": 5,
                "max_channel_distance": None,
                "templates_from_data": True,
                "n_templates": 6,
                "n_pcs": 6,
                "Th_single_ch": 6,
                "acg_threshold": 0.2,
                "ccg_threshold": 0.25,
                "cluster_downsampling": 20,
                "save_preprocessed_copy": False,
                "torch_device": "auto",
                "bad_channels": None,
                "clear_cache": False,
                "save_extra_vars": False,
                "do_correction": True,
                "keep_good_only": False,
                "skip_kilosort_preprocessing": False,
                "use_binary_file": None,
                "delete_recording_dat": True
            }
        },





# class SpikeSortingScanConfig(ScanConfig):





# class Kilosort4ScanConfig(ScanConfig):
#     """ScanConfig for extracting sub-circuits from larger circuits."""

#     single_coord_class_title: ClassVar[str] = "Kilosort4SingleConfig"
#     title: ClassVar[str] = "Kilosort4"
#     description: ClassVar[str] = (
#         "Kilosort4"
#     )

#     class Initialize(Block):


