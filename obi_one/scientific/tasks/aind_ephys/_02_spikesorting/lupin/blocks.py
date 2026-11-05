"""Lupin's parameters, by theme.

Defaults are those of the AIND pipeline's ``default_params.json``.
"""

from typing import Literal

from pydantic import Field, NonNegativeFloat, NonNegativeInt, PositiveFloat, PositiveInt

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.tasks.aind_ephys._02_spikesorting.blocks import SorterParameters
from obi_one.scientific.tasks.aind_ephys.blocks import PEAK_SIGN_OPTIONS, string_selection

MOTION_PRESET_OPTIONS = {
    "dredge_fast": ("DREDGE, fast", "A modified, faster DREDGE."),
    "dredge": ("DREDGE", "The official DREDGE preset."),
    "rigid_fast": ("Rigid, fast", "Rigid and fast, but less accurate; uses the center of mass."),
}
MATCHING_ENGINE_OPTIONS = {
    "circus-omp": ("Circus OMP", "Orthogonal matching pursuit, from Spyking Circus."),
    "wobble": (
        "Wobble",
        "The Paninski lab's matching, which jitters templates in time and amplitude.",
    ),
}


class LupinPreprocessing(SorterParameters):
    """Whether and how the sorter filters, references and whitens the recording."""

    apply_preprocessing: bool = Field(
        default=True,
        title="Apply preprocessing",
        description=("Whether the sorter whitens and otherwise preprocesses the recording at all."),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    filter_internally: bool = Field(
        default=False,
        title="Filter internally",
        description=(
            "Whether the sorter band-pass filters and common-references the recording"
            " itself. Off, it takes the recording as already preprocessed."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    freq_min: PositiveFloat | list[PositiveFloat] = Field(
        default=150.0,
        title="Filter low cutoff",
        description="Low cutoff of the sorter's band-pass filter, when it filters internally.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )
    freq_max: PositiveFloat | list[PositiveFloat] = Field(
        default=7000.0,
        title="Filter high cutoff",
        description=("High cutoff of the sorter's band-pass filter, when it filters internally."),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )
    whitening_radius_um: PositiveFloat | list[PositiveFloat] = Field(
        default=100.0,
        title="Whitening radius",
        description="Radius of the channels each channel is whitened with.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    cache_preprocessing_mode: Literal["no-cache", "auto", "memory", "zarr"] = Field(
        default="no-cache",
        title="Cache mode",
        description="Where the sorter caches its preprocessed recording.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    def to_dict(self) -> dict:
        # An empty chain runs no steps, where None has the sorter run its own.
        parameters = super().to_dict()
        filter_internally = parameters.pop("filter_internally")
        return {**parameters, "preprocessing_dict": None if filter_internally else {}}


class LupinMotionCorrection(SorterParameters):
    """The sorter's own motion correction."""

    apply_motion_correction: bool = Field(
        default=True,
        title="Apply motion correction",
        description="Whether the sorter corrects motion; needs its own preprocessing on.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    motion_correction_preset: Literal["dredge_fast", "dredge", "rigid_fast"] = Field(
        default="dredge_fast",
        title="Motion preset",
        description="Motion correction preset.",
        json_schema_extra=string_selection(MOTION_PRESET_OPTIONS),
    )


class LupinSpikeDetection(SorterParameters):
    """Peak detection."""

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
    detection_radius_um: PositiveFloat | list[PositiveFloat] = Field(
        default=50.0,
        title="Detection radius",
        description="Radius of the channels used for peak detection.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    seed: NonNegativeInt | list[NonNegativeInt] = Field(
        default=42,
        title="Random seed",
        description="Seed of the sorter's random steps.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )


class LupinClustering(SorterParameters):
    """Grouping peaks into units."""

    clustering_ms_before: PositiveFloat | list[PositiveFloat] = Field(
        default=0.3,
        title="Time before peak",
        description="Length of the waveform clustered before the peak.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    clustering_ms_after: PositiveFloat | list[PositiveFloat] = Field(
        default=1.3,
        title="Time after peak",
        description="Length of the waveform clustered after the peak.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    features_radius_um: PositiveFloat | list[PositiveFloat] = Field(
        default=120.0,
        title="Features radius",
        description="Radius of the channels used for the SVD features.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    split_radius_um: PositiveFloat | list[PositiveFloat] = Field(
        default=60.0,
        title="Split radius",
        description="Radius of the channels used by the local split.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    n_peaks_per_channel: PositiveInt | list[PositiveInt] = Field(
        default=5000,
        title="Peaks per channel",
        description="Number of peaks clustered per channel.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    n_svd_components_per_channel: PositiveInt | list[PositiveInt] = Field(
        default=5,
        title="SVD components per channel",
        description="Number of SVD components per channel.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    n_pca_features: PositiveInt | list[PositiveInt] = Field(
        default=4,
        title="PCA features",
        description="Number of secondary PCA features before the local split.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    clustering_recursive_depth: PositiveInt | list[PositiveInt] = Field(
        default=3,
        title="Recursive depth",
        description="How many times clusters are split recursively.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )


class LupinTemplateMatching(SorterParameters):
    """The templates, and matching them to the recording."""

    ms_before: PositiveFloat | list[PositiveFloat] = Field(
        default=1.0,
        title="Time before peak",
        description="Length of the template before the peak.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    ms_after: PositiveFloat | list[PositiveFloat] = Field(
        default=2.5,
        title="Time after peak",
        description="Length of the template after the peak.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    template_radius_um: PositiveFloat | list[PositiveFloat] = Field(
        default=100.0,
        title="Template radius",
        description="Radius of each template's channels before matching.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    template_sparsify_threshold: PositiveFloat | list[PositiveFloat] = Field(
        default=1.5,
        title="Template sparsify threshold",
        description="Threshold for sparsifying templates before template matching.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    template_min_snr_ptp: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=4.0,
        title="Minimum template SNR",
        description="Templates below this peak-to-peak signal-to-noise ratio are removed.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    template_max_jitter_ms: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.2,
        title="Maximum template jitter",
        description="Templates jittering more than this are removed.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    merge_similarity_lag_ms: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.5,
        title="Merge similarity lag",
        description="Largest lag when comparing templates to merge.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    min_firing_rate: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.1,
        title="Minimum firing rate",
        description="Small clusters below this rate are removed before matching.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )
    template_matching_engine: Literal["circus-omp", "wobble"] = Field(
        default="circus-omp",
        title="Template matching engine",
        description="Template matching method.",
        json_schema_extra=string_selection(MATCHING_ENGINE_OPTIONS),
    )
