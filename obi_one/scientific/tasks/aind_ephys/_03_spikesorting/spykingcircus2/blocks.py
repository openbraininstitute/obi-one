"""SpykingCircus2's parameters, by theme.

Defaults are those of the AIND pipeline's ``default_params.json``, but for the motion preset: its
DREDGE needs torch, which a launch job does not install.
"""

from typing import Literal

from pydantic import Field, NonNegativeFloat, NonNegativeInt, PositiveFloat, PositiveInt

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.blocks import SorterParameters
from obi_one.scientific.tasks.aind_ephys.blocks import (
    MOTION_PRESET_OPTIONS,
    PEAK_SIGN_OPTIONS,
    MotionPreset,
    string_selection,
)

FILTER_TYPE_OPTIONS = {
    "bessel": ("Bessel", "Keeps spike shapes well, with a gentler cutoff."),
    "butter": ("Butterworth", "A sharper cutoff, which can distort spike shapes more."),
}
WHITENING_MODE_OPTIONS = {
    "local": ("Local", "Decorrelates each channel with the channels near it."),
    "global": ("Global", "Decorrelates all channels together."),
}
DETECTION_METHOD_OPTIONS = {
    "matched_filtering": (
        "Matched filtering",
        "Detects peaks with a waveform prototype learned from the recording; slightly slower.",
    ),
    "locally_exclusive": (
        "Locally exclusive",
        "Keeps the largest threshold crossing within a neighbourhood of channels.",
    ),
}
# spikeinterface's SpykingCircus2 passes the other clustering and matching methods too little
# to run them.
MATCHING_METHOD_OPTIONS = {
    "circus-omp": ("Circus OMP", "Orthogonal matching pursuit, from Spyking Circus."),
    "wobble": (
        "Wobble",
        "The Paninski lab's matching, which jitters templates in time and amplitude.",
    ),
}


class SpykingCircus2Preprocessing(SorterParameters):
    """Whether and how the sorter filters, references and whitens the recording."""

    apply_preprocessing: bool = Field(
        default=False,
        title="Apply preprocessing",
        description=(
            "Whether the sorter band-pass filters and common-references the recording"
            " again. Whitening has its own setting."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    freq_min: PositiveFloat | list[PositiveFloat] = Field(
        default=150.0,
        title="Filter low cutoff",
        description="Low cutoff of the sorter's band-pass filter.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )
    freq_max: PositiveFloat | list[PositiveFloat] = Field(
        default=7000.0,
        title="Filter high cutoff",
        description="High cutoff of the sorter's band-pass filter.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )
    filter_type: Literal["bessel", "butter"] = Field(
        default="bessel",
        title="Filter type",
        description="Design of the sorter's band-pass filter.",
        json_schema_extra=string_selection(FILTER_TYPE_OPTIONS),
    )
    filter_order: PositiveInt | list[PositiveInt] = Field(
        default=2,
        title="Filter order",
        description="Order of the sorter's band-pass filter.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    apply_whitening: bool = Field(
        default=True,
        title="Apply whitening",
        description="Whether the sorter whitens the recording before template matching.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    whitening_mode: Literal["local", "global"] = Field(
        default="local",
        title="Whitening mode",
        description="Which channels each channel is decorrelated with.",
        json_schema_extra=string_selection(WHITENING_MODE_OPTIONS),
    )
    whitening_regularize: bool = Field(
        default=False,
        title="Regularize whitening",
        description=(
            "Whether to shrink the covariance estimate behind the whitening (Ledoit-Wolf)."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    cache_preprocessing_mode: Literal["no-cache", "memory", "zarr"] = Field(
        default="no-cache",
        title="Cache mode",
        description="Where the sorter caches its preprocessed recording.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    def to_dict(self) -> dict:
        return {
            "apply_preprocessing": self.apply_preprocessing,
            "filtering": {
                "freq_min": self.freq_min,
                "freq_max": self.freq_max,
                "ftype": self.filter_type,
                "filter_order": self.filter_order,
            },
            "apply_whitening": self.apply_whitening,
            "whitening": {"mode": self.whitening_mode, "regularize": self.whitening_regularize},
            "cache_preprocessing": {"mode": self.cache_preprocessing_mode},
        }


class SpykingCircus2MotionCorrection(SorterParameters):
    """The sorter's own motion correction."""

    apply_motion_correction: bool = Field(
        default=True,
        title="Apply motion correction",
        description="Whether the sorter corrects motion (dense probes only).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    motion_correction_preset: MotionPreset = Field(
        default="nonrigid_fast_and_accurate",
        title="Motion preset",
        description="Motion correction preset.",
        json_schema_extra=string_selection(MOTION_PRESET_OPTIONS),
    )

    def to_dict(self) -> dict:
        return {
            "apply_motion_correction": self.apply_motion_correction,
            "motion_correction": {"preset": self.motion_correction_preset},
        }


class SpykingCircus2SpikeDetection(SorterParameters):
    """Peak detection, and the channels used around each spike."""

    detection_method: Literal["matched_filtering", "locally_exclusive"] = Field(
        default="matched_filtering",
        title="Detection method",
        description="How peaks are found.",
        json_schema_extra=string_selection(DETECTION_METHOD_OPTIONS),
    )
    detect_threshold: PositiveFloat | list[PositiveFloat] = Field(
        default=5.0,
        title="Detection threshold",
        description="Peak detection threshold, in multiples of the noise level.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    peak_sign: Literal["neg", "pos", "both"] = Field(
        default="neg",
        title="Peak sign",
        description="Sign of the peaks to detect.",
        json_schema_extra=string_selection(PEAK_SIGN_OPTIONS),
    )
    radius_um: PositiveFloat | list[PositiveFloat] = Field(
        default=100.0,
        title="Radius",
        description="Radius of the channels used around each spike.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    seed: NonNegativeInt | list[NonNegativeInt] = Field(
        default=42,
        title="Random seed",
        description="Seed of the chunk shuffling during peak detection.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    deterministic_peaks_detection: bool = Field(
        default=False,
        title="Deterministic detection",
        description=("Whether peak detection is repeatable, with the seed shuffling the chunks."),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    def to_dict(self) -> dict:
        return {
            "general": {"radius_um": self.radius_um},
            "detection": {
                "method": self.detection_method,
                "method_kwargs": {
                    "peak_sign": self.peak_sign,
                    "detect_threshold": self.detect_threshold,
                },
            },
            "seed": self.seed,
            "deterministic_peaks_detection": self.deterministic_peaks_detection,
        }


class SpykingCircus2PeakSelection(SorterParameters):
    """How many detected peaks go on to clustering."""

    n_peaks_per_channel: PositiveInt | list[PositiveInt] = Field(
        default=5000,
        title="Peaks per channel",
        description="Number of peaks kept for clustering, per channel.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    min_n_peaks: PositiveInt | list[PositiveInt] = Field(
        default=100000,
        title="Minimum peaks",
        description="Fewest peaks kept for clustering, however few channels there are.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    select_per_channel: bool = Field(
        default=False,
        title="Select per channel",
        description="Whether peaks are selected channel by channel.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    def to_dict(self) -> dict:
        return {
            "selection": {
                "method_kwargs": {
                    "n_peaks_per_channel": self.n_peaks_per_channel,
                    "min_n_peaks": self.min_n_peaks,
                    "select_per_channel": self.select_per_channel,
                }
            }
        }


class SpykingCircus2Clustering(SorterParameters):
    """Grouping the selected peaks into units."""

    clustering_method_kwargs: dict = Field(
        default={},
        title="Clustering method kwargs",
        description="Overrides of the clustering method's arguments, as JSON.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.JSON_OBJECT},
    )
    merge_max_distance_um: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=50.0,
        title="Merge distance",
        description="Farthest apart two units can be and still merge after matching.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    multi_units_only: bool = Field(
        default=False,
        title="Multi-units only",
        description="Whether to skip clustering and return one multi-unit per electrode.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    def to_dict(self) -> dict:
        return {
            "clustering": {"method_kwargs": self.clustering_method_kwargs},
            "merging": {"max_distance_um": self.merge_max_distance_um},
            "multi_units_only": self.multi_units_only,
        }


class SpykingCircus2Templates(SorterParameters):
    """The templates' shape, and which of them are kept."""

    ms_before: PositiveFloat | list[PositiveFloat] = Field(
        default=0.5,
        title="Time before peak",
        description="Length of the template before the peak.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    ms_after: PositiveFloat | list[PositiveFloat] = Field(
        default=1.5,
        title="Time after peak",
        description="Length of the template after the peak.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    min_snr: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=5.0,
        title="Minimum SNR",
        description="Templates below this signal-to-noise ratio are removed.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    max_jitter_ms: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.2,
        title="Maximum jitter",
        description=(
            "Templates whose peak is farther than this from the expected time are removed."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    sparsify_threshold: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=1.0,
        title="Sparsify threshold",
        description="Channels of a template below this multiple of the noise are dropped.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    mean_sd_ratio_threshold: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=3.0,
        title="Mean to SD ratio threshold",
        description="Templates below this ratio of mean to standard deviation are removed.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    min_firing_rate: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.1,
        title="Minimum firing rate",
        description="Units firing below this rate are removed.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )

    def to_dict(self) -> dict:
        return {
            "general": {"ms_before": self.ms_before, "ms_after": self.ms_after},
            "cleaning": {
                "min_snr": self.min_snr,
                "max_jitter_ms": self.max_jitter_ms,
                "sparsify_threshold": self.sparsify_threshold,
                "mean_sd_ratio_threshold": self.mean_sd_ratio_threshold,
            },
            "min_firing_rate": self.min_firing_rate,
        }


class SpykingCircus2Matching(SorterParameters):
    """Finding every spike of every unit by template matching."""

    matching_method: Literal["circus-omp", "wobble"] = Field(
        default="circus-omp",
        title="Matching method",
        description="How templates are matched to the recording.",
        json_schema_extra=string_selection(MATCHING_METHOD_OPTIONS),
    )
    matching_method_kwargs: dict = Field(
        default={},
        title="Matching method kwargs",
        description="Overrides of the matching method's arguments, as JSON.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.JSON_OBJECT},
    )

    def to_dict(self) -> dict:
        # spikeinterface reads ``matching_kwargs``, not the ``method_kwargs`` its defaults list.
        return {
            "matching": {
                "method": self.matching_method,
                "matching_kwargs": self.matching_method_kwargs,
            }
        }
