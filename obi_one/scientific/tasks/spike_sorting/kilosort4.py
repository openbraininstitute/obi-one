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
                "nblocks": self.single_config.kilosort4_basic_setup.nblocks,
                "batch_size": self.single_config.kilosort4_basic_setup.batch_size,
                "Th_learned": self.single_config.kilosort4_basic_setup.th_learned,
                "Th_universal": self.single_config.kilosort4_basic_setup.th_universal,

                "nt": self.single_config.kilosort4_advanced_setup.nt,
                "dmin": self.single_config.kilosort4_advanced_setup.dmin,
                "dminx": self.single_config.kilosort4_advanced_setup.dminx,
                "min_template_size": self.single_config.kilosort4_advanced_setup.min_template_size,
                "nearest_chans": self.single_config.kilosort4_advanced_setup.nearest_chans,
                "nearest_templates": self.single_config.kilosort4_advanced_setup.nearest_templates,
                "x_centers": self.single_config.kilosort4_advanced_setup.x_centers,
                "duplicate_spike_ms": self.single_config.kilosort4_advanced_setup.duplicate_spike_ms,

                "do_CAR": True,
                "clear_cache": False,
                "invert_sign": False,
                "do_correction": True,
                "keep_good_only": False,
                "save_extra_vars": False,
                "templates_from_data": True,
                "delete_recording_dat": True,
                "save_preprocessed_copy": False,
                "skip_kilosort_preprocessing": False,
                
                "shift": None,
                "scale": None,
                "nt0min": None,
                "bad_channels": None,
                "use_binary_file": None,
                "artifact_threshold": None,
                "max_channel_distance": None,
                
                "n_pcs": 6,
                "nskip": 25,
                "sig_interp": 20,
                "n_templates": 6,
                "Th_single_ch": 6,
                "binning_depth": 5,
                "template_sizes": 5,
                "whitening_range": 32,
                "highpass_cutoff": 300,
                "cluster_downsampling": 20,

                "acg_threshold": 0.2,
                "ccg_threshold": 0.25,

                "drift_smoothing": [0.5, 0.5, 0.5],
                
                "torch_device": "auto",            
            }
        },
