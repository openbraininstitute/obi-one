from obi_one.core.block import Block
from pydantic import Discriminator, model_validator
from pydantic import Field, PositiveFloat, NonNegativeInt, NonNegativeFloat
from typing import Annotated, Literal
import numpy as np


# Preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing
# https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing/blob/main/code/params.json


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
        description="Phase shift to apply to the data in milliseconds.",
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

    def dictionary_representation(self) -> dict:

        d = {
            "denoising_strategy": self.single_config.initialize.denoising_strategy,
            "min_preprocessing_duration": self.single_config.initialize.min_preprocessing,
            "phase_shift": {
                "margin_ms": self.single_config.initialize.phase_shift,
            },
            "remove_out_channels": self.single_config.initialize.remove_out_channels,
            "common_reference": {
                "reference": self.single_config.initialize.common_reference,
                "operator": self.single_config.initialize.common_reference_operator,
            },
        }

        return d


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

    def dictionary_representation(self) -> dict:
        d = {
            "highpass_filter": {
                "freq_min": self.single_config.frequency_filter.min_freq,
                "margin_ms": self.single_config.frequency_filter.margin,
            }
        }
        return d

class SpikeSortingPreprocessingBandpassFilter(SpikeSortingPreprocessingHighPassFilter):
    max_freq: PositiveFloat | list[PositiveFloat] = Field(
        default=300.0,
        title="Maximum frequency (Hz)",
        description="Maximum frequency for band-pass filter in Hz.",
        unit="Hz"
    )

    # MAKE SURE max > min freq with validator
    @model_validator(mode="after")
    def check_freqs(cls, values):
        min_freq = values.get("min_freq")
        max_freq = values.get("max_freq")
        if max_freq <= min_freq:
            raise ValueError("max_freq must be greater than min_freq")
        return values
    

    def dictionary_representation(self) -> dict:
        d = super().dictionary_representation()
        d["highpass_filter"]["freq_max"] = self.single_config.frequency_filter.max_freq
        return d

SpikeSortingPreprocessingFilterUnion = Annotated[
    SpikeSortingPreprocessingHighPassFilter
    | SpikeSortingPreprocessingBandpassFilter,
    Discriminator("type"),
]


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

    def dictionary_representation(self) -> dict:

        d["highpass_spatial_filter"] = {
            "n_channel_pad": self.single_config.high_pass_spatial_filter.n_channel_pad,
            "n_channel_taper": self.single_config.high_pass_spatial_filter.n_channel_taper,
            "direction": self.single_config.high_pass_spatial_filter.direction,
            "apply_agc": self.single_config.high_pass_spatial_filter.apply_agc,
            "agc_window_length_s": self.single_config.high_pass_spatial_filter.agc_window_length_s,
            "highpass_butter_order": self.single_config.high_pass_spatial_filter.highpass_butter_order,
            "highpass_butter_wn": self.single_config.high_pass_spatial_filter.highpass_butter_wn,
        }
        return d


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
        default=1,
        title="Random seed",
        description="Random seed for reproducibility.",
    )

    def dictionary_representation(self) -> dict:
        # TODO: add detection parameters to dictionary representation

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


    def dictionary_representation(self) -> dict:
        d = {}
        d["motion_correction"] = {
            "preset": self.single_config.motion_correction.preset,
            "detect_kwargs": self.single_config.motion_correction.detect_kwargs,
            "select_kwargs": self.single_config.motion_correction.select_kwargs,
            "localize_peaks_kwargs": self.single_config.motion_correction.localize_peaks_kwargs,
            "estimate_motion_kwargs": self.single_config.motion_correction.estimate_motion_kwargs,
            "interpolate_motion_kwargs": self.single_config.motion_correction.interpolate_motion_kwargs,
        }
        return d
