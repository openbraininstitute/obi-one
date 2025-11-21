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


# Preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing/blob/main/code/params.json

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
