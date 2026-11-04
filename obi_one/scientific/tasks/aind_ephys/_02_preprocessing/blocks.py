"""Blocks for the preprocessing stage of the AIND ephys pipeline.

Each block's ``to_dict`` gives the keyword arguments of the ``spikeinterface.preprocessing``
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
from obi_one.scientific.tasks.aind_ephys.blocks import (
    MOTION_PRESET_OPTIONS,
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
    n_channel_taper: NonNegativeInt | None = Field(
        default=None,
        title="Channels to taper",
        description="Number of channels tapered on each side. Unset tapers the padded channels.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_OPTIONAL},
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
    detect_kwargs: dict = Field(
        default={},
        title="Detect kwargs",
        description="Overrides of the preset's peak detection kwargs.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.JSON_OBJECT},
    )
    select_kwargs: dict = Field(
        default={},
        title="Select kwargs",
        description="Overrides of the preset's peak selection kwargs.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.JSON_OBJECT},
    )
    localize_peaks_kwargs: dict = Field(
        default={},
        title="Localize peaks kwargs",
        description="Overrides of the preset's peak localization kwargs.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.JSON_OBJECT},
    )
    estimate_motion_kwargs: dict = Field(
        default={},
        title="Estimate motion kwargs",
        description="Overrides of the preset's motion estimation kwargs.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.JSON_OBJECT},
    )
    interpolate_motion_kwargs: dict = Field(
        default={},
        title="Interpolate motion kwargs",
        description="Kwargs of the motion interpolation, when motion is applied.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.JSON_OBJECT},
    )

    def estimate_motion_dict(self, probe_span_um: float) -> dict:
        """Estimation kwargs, with the window sizes scaled to the probe's span."""
        kwargs = {**self.estimate_motion_kwargs, "bin_s": self.temporal_bin_s}
        if self.win_step_norm is not None:
            kwargs["win_step_um"] = self.win_step_norm * probe_span_um
        if self.win_scale_norm is not None:
            kwargs["win_scale_um"] = self.win_scale_norm * probe_span_um
        return kwargs


TemporalFilterUnion = Annotated[HighpassFilterParams | BandpassFilterParams, Discriminator("type")]
DenoisingUnion = Annotated[CommonReference | HighpassSpatialFilter, Discriminator("type")]
