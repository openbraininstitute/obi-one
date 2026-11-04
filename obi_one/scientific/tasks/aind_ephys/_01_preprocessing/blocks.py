"""Blocks for the preprocessing stage of the AIND ephys pipeline.

Each step's block ``to_dict`` gives the keyword arguments of the ``spikeinterface.preprocessing``
function its step calls. Defaults are those of the AIND pipeline's ``default_params.json``, but
for the motion preset: its DREDGE needs torch, which a launch job does not install.
"""

from typing import Annotated, ClassVar, Literal

from pydantic import (
    Discriminator,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
)

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.library.extracellular_recording_properties import MIN_SAMPLING_FREQUENCY
from obi_one.scientific.tasks.aind_ephys.blocks import (
    MOTION_PRESET_OPTIONS,
    PEAK_SIGN_OPTIONS,
    MotionPreset,
    string_selection,
)

BAD_CHANNEL_METHOD_OPTIONS = {
    "coherence+psd": (
        "Coherence and power spectrum",
        "Finds dead, noisy and outside channels from coherence and power spectrum.",
    ),
    "std": (
        "Standard deviation",
        "Flags channels whose standard deviation is far from the others'.",
    ),
    "mad": (
        "Median absolute deviation",
        "Flags channels whose median absolute deviation is far from the others'.",
    ),
}
OUTSIDE_CHANNELS_OPTIONS = {
    "top": ("Top", "Only the top of the probe can be outside the brain."),
    "bottom": ("Bottom", "Only the bottom of the probe can be outside the brain."),
    "both": ("Both", "Either end of the probe can be outside the brain."),
}
REFERENCE_OPTIONS = {
    "global": ("Global", "Every channel shares one reference, made from all channels."),
    "local": ("Local", "Each channel's reference is made from the channels around it."),
    "single": ("Single", "One chosen channel is the reference for all."),
}
OPERATOR_OPTIONS = {
    "median": ("Median", "The median of the reference channels, robust to outliers."),
    "average": ("Average", "The mean of the reference channels."),
}
DIRECTION_OPTIONS = {
    "x": ("x", "Across the width of the probe."),
    "y": ("y", "Along the depth of the probe."),
    "z": ("z", "Along the third axis of the probe."),
}
MOTION_DIRECTION_OPTIONS = {key: DIRECTION_OPTIONS[key] for key in ("x", "y")}
BORDER_MODE_OPTIONS = {
    "remove_channels": ("Remove channels", "Removes channels that motion carries off the probe."),
    "force_extrapolate": (
        "Extrapolate",
        "Keeps every channel, extrapolating where motion carries it off the probe.",
    ),
    "force_zeros": (
        "Zeros",
        "Keeps every channel, with zeros where motion carries it off the probe.",
    ),
}
SPATIAL_INTERPOLATION_OPTIONS = {
    "kriging": ("Kriging", "Weighs all channels with a kernel of their distance."),
    "idw": ("Inverse distance", "Weighs the closest channels by their inverse distance."),
    "nearest": ("Nearest", "Takes the nearest channel."),
}


class PhaseShift(Block):
    """``phase_shift``, applied only when the recording has ``inter_sample_shift``."""

    margin_ms: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=100.0,
        title="Phase-shift margin",
        description="Margin of the phase-shift filter.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def to_dict(self) -> dict:
        return {"margin_ms": self.margin_ms}


class HighpassFilterParams(Block):
    """Keep the frequencies above a cutoff."""

    title: ClassVar[str] = "Highpass"
    pipeline_step: ClassVar[str] = "highpass_filter"

    freq_min: PositiveFloat | list[PositiveFloat] = Field(
        default=300.0,
        title="Highpass cutoff",
        description="Cutoff frequency of the highpass filter.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )
    margin_ms: NonNegativeFloat | None = Field(
        default=None,
        title="Filter margin",
        description="Margin of the filter. Unset sizes it from the cutoff frequency.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def to_dict(self) -> dict:
        return {
            "freq_min": self.freq_min,
            "margin_ms": "auto" if self.margin_ms is None else self.margin_ms,
        }


class BandpassFilterParams(Block):
    """Keep the frequencies between two cutoffs."""

    title: ClassVar[str] = "Bandpass"
    pipeline_step: ClassVar[str] = "bandpass_filter"

    freq_min: PositiveFloat | list[PositiveFloat] = Field(
        default=300.0,
        title="Lower cutoff",
        description="Lower cutoff frequency of the bandpass filter.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )
    freq_max: PositiveFloat | list[PositiveFloat] = Field(
        default=6000.0,
        title="Upper cutoff",
        description="Upper cutoff frequency of the bandpass filter.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )
    margin_ms: NonNegativeFloat | None = Field(
        default=None,
        title="Filter margin",
        description="Margin of the filter. Unset sizes it from the cutoff frequency.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def to_dict(self) -> dict:
        return {
            "freq_min": self.freq_min,
            "freq_max": self.freq_max,
            "margin_ms": "auto" if self.margin_ms is None else self.margin_ms,
        }


class DetectBadChannels(Block):
    """``detect_and_remove_bad_channels``; which labels are removed is set on the config."""

    method: Literal["coherence+psd", "std", "mad"] = Field(
        default="coherence+psd",
        title="Detection method",
        description="Bad-channel detection method.",
        json_schema_extra=string_selection(BAD_CHANNEL_METHOD_OPTIONS),
    )
    dead_channel_threshold: float | list[float] = Field(
        default=-0.5,
        title="Dead channel threshold",
        description="Coherence below which a channel is dead.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    noisy_channel_threshold: float | list[float] = Field(
        default=1.0,
        title="Noisy channel threshold",
        description="Power above which a channel is noisy.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    outside_channel_threshold: float | list[float] = Field(
        default=-0.3,
        title="Outside channel threshold",
        description="Coherence below which a channel at the probe's edge is outside the brain.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    outside_channels_location: Literal["top", "bottom", "both"] = Field(
        default="top",
        title="Outside channels location",
        description="Which end of the probe can be outside the brain.",
        json_schema_extra=string_selection(OUTSIDE_CHANNELS_OPTIONS),
    )
    n_neighbors: PositiveInt | list[PositiveInt] = Field(
        default=11,
        title="Neighbours",
        description="Number of neighbouring channels used for coherence.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    seed: NonNegativeInt | list[NonNegativeInt] = Field(
        default=0,
        title="Random seed",
        description="Seed of the random chunks used for detection.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    def to_dict(self, *, remove_out_channels: bool, remove_bad_channels: bool) -> dict:
        channel_filters = set()
        if remove_bad_channels:
            channel_filters |= {"dead", "noise"}
        if remove_out_channels:
            channel_filters.add("out")
        return {
            "method": self.method,
            "dead_channel_threshold": self.dead_channel_threshold,
            "noisy_channel_threshold": self.noisy_channel_threshold,
            "outside_channel_threshold": self.outside_channel_threshold,
            "outside_channels_location": self.outside_channels_location,
            "n_neighbors": self.n_neighbors,
            "channel_filters": channel_filters,
            "seed": self.seed,
        }


class CommonReference(Block):
    """Subtract a signal shared across channels; by default their median."""

    title: ClassVar[str] = "Common reference"
    pipeline_step: ClassVar[str] = "common_reference"

    reference: Literal["global", "local", "single"] = Field(
        default="global",
        title="Reference",
        description="Which channels form each channel's reference.",
        json_schema_extra=string_selection(REFERENCE_OPTIONS),
    )
    operator: Literal["median", "average"] = Field(
        default="median",
        title="Operator",
        description="How the reference channels are combined.",
        json_schema_extra=string_selection(OPERATOR_OPTIONS),
    )

    def to_dict(self) -> dict:
        return {"reference": self.reference, "operator": self.operator}


class HighpassSpatialFilter(Block):
    """Destripe: filter across channels, removing noise that varies slowly along the probe."""

    title: ClassVar[str] = "Highpass spatial filter"
    pipeline_step: ClassVar[str] = "highpass_spatial_filter"

    n_channel_pad: NonNegativeInt | list[NonNegativeInt] = Field(
        default=60,
        title="Channels to pad",
        description="Number of channels padded on each side.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    n_channel_taper: NonNegativeInt | list[NonNegativeInt] = Field(
        default=60,
        title="Channels to taper",
        description="Number of channels tapered on each side, usually the channels padded.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    direction: Literal["x", "y", "z"] = Field(
        default="y",
        title="Direction",
        description="Probe axis along which the spatial filter runs.",
        json_schema_extra=string_selection(DIRECTION_OPTIONS),
    )
    apply_agc: bool = Field(
        default=True,
        title="Apply AGC",
        description="Whether to apply automatic gain control.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    agc_window_length_s: PositiveFloat | list[PositiveFloat] = Field(
        default=0.01,
        title="AGC window length",
        description="Window of the automatic gain control.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.SECONDS,
        },
    )
    highpass_butter_order: PositiveInt | list[PositiveInt] = Field(
        default=3,
        title="Butterworth order",
        description="Order of the spatial highpass Butterworth filter.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    highpass_butter_wn: PositiveFloat | list[PositiveFloat] = Field(
        default=0.01,
        title="Butterworth Wn",
        description="Normalised cutoff of the spatial Butterworth filter.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    def to_dict(self) -> dict:
        return {
            "n_channel_pad": self.n_channel_pad,
            "n_channel_taper": self.n_channel_taper,
            "direction": self.direction,
            "apply_agc": self.apply_agc,
            "agc_window_length_s": self.agc_window_length_s,
            "highpass_butter_order": self.highpass_butter_order,
            "highpass_butter_wn": self.highpass_butter_wn,
        }


class MotionCorrection(Block):
    """Motion estimation with ``spikeinterface.preprocessing.compute_motion``."""

    compute: bool = Field(
        default=True,
        title="Compute motion",
        description="Whether to estimate the probe's motion.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    apply: bool = Field(
        default=False,
        title="Apply motion",
        description="Whether to interpolate the recording to correct the estimated motion.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    preset: MotionPreset = Field(
        default="nonrigid_fast_and_accurate",
        title="Motion preset",
        description="Motion estimation preset.",
        json_schema_extra=string_selection(MOTION_PRESET_OPTIONS),
    )
    temporal_bin_s: PositiveFloat | list[PositiveFloat] = Field(
        default=1.0,
        title="Temporal bin",
        description="Temporal bin of the motion estimate.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.SECONDS,
        },
    )
    win_step_norm: PositiveFloat | None = Field(
        default=0.1,
        title="Window step",
        description="Step of the non-rigid windows, as a fraction of the probe's span.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL},
    )
    win_scale_norm: PositiveFloat | None = Field(
        default=0.1,
        title="Window scale",
        description="Scale of the non-rigid windows, as a fraction of the probe's span.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL},
    )
    direction: Literal["x", "y"] = Field(
        default="y",
        title="Motion direction",
        description="Probe axis along which the motion is estimated.",
        json_schema_extra=string_selection(MOTION_DIRECTION_OPTIONS),
    )
    rigid: bool = Field(
        default=False,
        title="Rigid motion",
        description="Whether the whole probe moves as one, rather than window by window.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    peak_sign: Literal["neg", "pos", "both"] = Field(
        default="neg",
        title="Peak sign",
        description="Sign of the peaks the motion is estimated from.",
        json_schema_extra=string_selection(PEAK_SIGN_OPTIONS),
    )
    detect_threshold: PositiveFloat | list[PositiveFloat] = Field(
        default=8.0,
        title="Detection threshold",
        description="Peak detection threshold, in multiples of the noise level.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    exclude_sweep_ms: PositiveFloat | list[PositiveFloat] = Field(
        default=0.8,
        title="Peak exclusion time",
        description="Within this time of a peak, only the largest nearby one is kept.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    detect_radius_um: PositiveFloat | None = Field(
        default=None,
        title="Detection radius",
        description="Radius within which only the largest peak is kept. Unset uses the preset's.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    localize_radius_um: PositiveFloat | None = Field(
        default=None,
        title="Localization radius",
        description="Radius of the channels used to localize a peak. Unset uses the method's.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    border_mode: Literal["remove_channels", "force_extrapolate", "force_zeros"] = Field(
        default="remove_channels",
        title="Border mode",
        description="What happens at the probe's ends, when motion is applied.",
        json_schema_extra=string_selection(BORDER_MODE_OPTIONS),
    )
    spatial_interpolation_method: Literal["kriging", "idw", "nearest"] = Field(
        default="kriging",
        title="Interpolation method",
        description="How traces are interpolated across channels, when motion is applied.",
        json_schema_extra=string_selection(SPATIAL_INTERPOLATION_OPTIONS),
    )
    sigma_um: PositiveFloat | list[PositiveFloat] = Field(
        default=20.0,
        title="Kriging sigma",
        description="Width of the kriging kernel.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    p: PositiveInt | list[PositiveInt] = Field(
        default=1,
        title="Kriging decay",
        description="Exponent of the kriging kernel's decay with distance.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    num_closest: PositiveInt | list[PositiveInt] = Field(
        default=3,
        title="Closest channels",
        description="Number of channels the inverse distance method uses.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    def detect_dict(self) -> dict:
        """What the detection kwargs override of the preset's."""
        kwargs: dict = {
            "peak_sign": self.peak_sign,
            "detect_threshold": self.detect_threshold,
            "exclude_sweep_ms": self.exclude_sweep_ms,
        }
        if self.detect_radius_um is not None:
            kwargs["radius_um"] = self.detect_radius_um
        return kwargs

    def localize_dict(self) -> dict:
        """What the localization kwargs override of the preset's."""
        return {} if self.localize_radius_um is None else {"radius_um": self.localize_radius_um}

    def estimate_motion_dict(self, probe_span_um: float) -> dict:
        """Estimation kwargs, with the window sizes scaled to the probe's span."""
        kwargs: dict = {
            "bin_s": self.temporal_bin_s,
            "direction": self.direction,
            "rigid": self.rigid,
        }
        if self.win_step_norm is not None:
            kwargs["win_step_um"] = self.win_step_norm * probe_span_um
        if self.win_scale_norm is not None:
            kwargs["win_scale_um"] = self.win_scale_norm * probe_span_um
        return kwargs

    def interpolate_dict(self) -> dict:
        """Kwargs of the interpolation, when motion is applied."""
        return {
            "border_mode": self.border_mode,
            "spatial_interpolation_method": self.spatial_interpolation_method,
            "sigma_um": self.sigma_um,
            "p": self.p,
            "num_closest": self.num_closest,
        }


TemporalFilterUnion = Annotated[HighpassFilterParams | BandpassFilterParams, Discriminator("type")]
DenoisingUnion = Annotated[CommonReference | HighpassSpatialFilter, Discriminator("type")]


class JobDispatch(Block):
    """How the raw recordings of an NWB file are split into jobs."""

    electrical_series_path: str | None = Field(
        default=None,
        title="Electrical series",
        description=(
            "Path of the one ElectricalSeries to process, such as"
            " 'acquisition/ElectricalSeriesAP'. None processes every series in acquisition."
        ),
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    split_segments: bool = Field(
        default=True,
        title="Split segments",
        description="Whether each recording segment becomes its own job.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    split_groups: bool = Field(
        default=True,
        title="Split groups",
        description="Whether each channel group (probe or shank) becomes its own job.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    skip_timestamps_check: bool = Field(
        default=False,
        title="Skip timestamps check",
        description="Skip the check that resets timestamps with gaps or reversals.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    min_recording_duration: NonNegativeFloat | None = Field(
        default=None,
        title="Minimum recording duration",
        description="Recordings shorter than this are not dispatched. None keeps them all.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True, SchemaKey.UNITS: Units.SECONDS},
    )
    min_sampling_frequency: PositiveFloat = Field(
        default=MIN_SAMPLING_FREQUENCY,
        title="Minimum sampling frequency",
        description="Series sampled below this are taken to be LFP and skipped.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True, SchemaKey.UNITS: Units.HERTZ},
    )
    debug: bool = Field(
        default=False,
        title="Debug",
        description="Clip each segment to the debug duration, and keep short recordings.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    debug_duration: PositiveFloat = Field(
        default=30.0,
        title="Debug duration",
        description="Duration each segment is clipped to in debug mode.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True, SchemaKey.UNITS: Units.SECONDS},
    )
