"""Building blocks for the aind-ephys-preprocessing capsule.

The fields below mirror the keys read from the capsule's ``params.json``
(https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing/blob/main/code/params.json).
Each Block has a ``to_dict`` method that returns the JSON fragment the capsule
expects for that section.
"""

from typing import Literal

from pydantic import Field, NonNegativeFloat, NonNegativeInt, PositiveFloat, PositiveInt

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


class JobKwargs(Block):
    """SpikeInterface job_kwargs (passed to set_global_job_kwargs in the capsule)."""

    chunk_duration: str = Field(
        default="1s",
        title="Chunk duration",
        description="Chunk size as a string ('1s', '500ms', etc.).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    progress_bar: bool = Field(
        default=False,
        title="Progress bar",
        description="Whether to show a progress bar in spikeinterface jobs.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    mp_context: Literal["spawn", "fork", "forkserver"] = Field(
        default="spawn",
        title="Multiprocessing context",
        description="Python multiprocessing context for spikeinterface jobs.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )

    def to_dict(self) -> dict:
        return {
            "chunk_duration": self.chunk_duration,
            "progress_bar": self.progress_bar,
            "mp_context": self.mp_context,
        }


class PhaseShift(Block):
    """``phase_shift`` parameters."""

    margin_ms: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=100.0,
        title="Phase-shift margin",
        description="Phase-shift margin in ms.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def to_dict(self) -> dict:
        return {"margin_ms": self.margin_ms}


class HighpassFilterParams(Block):
    """``highpass_filter`` parameters (used when filter_type='highpass')."""

    freq_min: PositiveFloat | list[PositiveFloat] = Field(
        default=300.0,
        title="Highpass cutoff",
        description="Lower cutoff frequency in Hz.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )
    margin_ms: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=5.0,
        title="Filter margin",
        description="Filter margin in ms.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def to_dict(self) -> dict:
        return {"freq_min": self.freq_min, "margin_ms": self.margin_ms}


class BandpassFilterParams(Block):
    """``bandpass_filter`` parameters (used when filter_type='bandpass')."""

    freq_min: PositiveFloat | list[PositiveFloat] = Field(
        default=300.0,
        title="Lower cutoff",
        description="Lower cutoff frequency in Hz.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )
    freq_max: PositiveFloat | list[PositiveFloat] = Field(
        default=6000.0,
        title="Upper cutoff",
        description="Upper cutoff frequency in Hz.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )
    margin_ms: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=5.0,
        title="Filter margin",
        description="Filter margin in ms.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def to_dict(self) -> dict:
        return {
            "freq_min": self.freq_min,
            "freq_max": self.freq_max,
            "margin_ms": self.margin_ms,
        }


class DetectBadChannels(Block):
    """``detect_bad_channels`` parameters."""

    method: Literal["coherence+psd", "std", "mad"] = Field(
        default="coherence+psd",
        title="Detection method",
        description="Bad-channel detection method.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    dead_channel_threshold: float | list[float] = Field(
        default=-0.5,
        title="Dead channel threshold",
        description="Threshold below which a channel is considered dead.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    noisy_channel_threshold: float | list[float] = Field(
        default=1.0,
        title="Noisy channel threshold",
        description="Threshold above which a channel is considered noisy.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    outside_channel_threshold: float | list[float] = Field(
        default=-0.3,
        title="Outside channel threshold",
        description="Threshold below which a channel is considered outside the brain.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    outside_channels_location: Literal["top", "bottom", "both"] = Field(
        default="top",
        title="Outside channels location",
        description="Where to look for outside channels.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    n_neighbors: PositiveInt | list[PositiveInt] = Field(
        default=11,
        title="Neighbours",
        description="Number of neighbouring channels for coherence-based detection.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    seed: NonNegativeInt | list[NonNegativeInt] = Field(
        default=0,
        title="Random seed",
        description="Seed for reproducibility.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "dead_channel_threshold": self.dead_channel_threshold,
            "noisy_channel_threshold": self.noisy_channel_threshold,
            "outside_channel_threshold": self.outside_channel_threshold,
            "outside_channels_location": self.outside_channels_location,
            "n_neighbors": self.n_neighbors,
            "seed": self.seed,
        }


class CommonReference(Block):
    """``common_reference`` parameters."""

    reference: Literal["global", "local", "single"] = Field(
        default="global",
        title="Reference",
        description="Reference scheme.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    operator: Literal["median", "mean"] = Field(
        default="median",
        title="Operator",
        description="Operator used to combine reference channels.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )

    def to_dict(self) -> dict:
        return {"reference": self.reference, "operator": self.operator}


class HighpassSpatialFilter(Block):
    """``highpass_spatial_filter`` parameters (used by 'destripe' denoising)."""

    n_channel_pad: NonNegativeInt | list[NonNegativeInt] = Field(
        default=60,
        title="Channels to pad",
        description="Number of channels to pad on each side.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    n_channel_taper: NonNegativeInt | None = Field(
        default=None,
        title="Channels to taper",
        description="Number of channels to taper. None disables tapering.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    direction: Literal["x", "y", "z"] = Field(
        default="y",
        title="Direction",
        description="Probe axis along which to apply the spatial filter.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
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
        description="AGC window length in seconds.",
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
        description="Normalised cutoff for the Butterworth filter.",
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
    """``motion_correction`` parameters.

    When the capsule is invoked with ``--params``, ``compute`` and ``apply`` are
    popped from this dict (the ``--motion`` CLI flag is ignored). Setting
    ``compute=False`` is the equivalent of ``--motion skip``.
    """

    preset: Literal[
        "dredge",
        "medicine",
        "dredge_fast",
        "nonrigid_accurate",
        "nonrigid_fast_and_accurate",
        "rigid_fast",
        "kilosort_like",
    ] = Field(
        default="dredge_fast",
        title="Motion preset",
        description="Motion-correction preset (passed to spre.compute_motion).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    compute: bool = Field(
        default=True,
        title="Compute motion",
        description="Whether to compute motion at all.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    apply: bool = Field(
        default=False,
        title="Apply motion",
        description="Whether to apply motion correction to the recording.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    motion_temporal_bin_s: PositiveFloat | list[PositiveFloat] = Field(
        default=1.0,
        title="Temporal bin",
        description="Temporal bin size for motion estimation, in seconds.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.SECONDS,
        },
    )
    detect_kwargs: dict = Field(
        default_factory=dict,
        title="Detect kwargs",
        description="Extra kwargs forwarded to peak detection.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    select_kwargs: dict = Field(
        default_factory=dict,
        title="Select kwargs",
        description="Extra kwargs forwarded to peak selection.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    localize_peaks_kwargs: dict = Field(
        default_factory=dict,
        title="Localize peaks kwargs",
        description="Extra kwargs forwarded to peak localisation.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    estimate_motion_kwargs: dict = Field(
        default_factory=lambda: {"win_step_norm": 0.1, "win_scale_norm": 0.1},
        title="Estimate motion kwargs",
        description="Extra kwargs forwarded to motion estimation.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    interpolate_motion_kwargs: dict = Field(
        default_factory=dict,
        title="Interpolate motion kwargs",
        description="Extra kwargs forwarded to motion interpolation.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    def to_dict(self) -> dict:
        return {
            "preset": self.preset,
            "compute": self.compute,
            "apply": self.apply,
            "detect_kwargs": self.detect_kwargs,
            "select_kwargs": self.select_kwargs,
            "localize_peaks_kwargs": self.localize_peaks_kwargs,
            "estimate_motion_kwargs": self.estimate_motion_kwargs,
            "interpolate_motion_kwargs": self.interpolate_motion_kwargs,
        }
