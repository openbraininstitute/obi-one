"""Building blocks for the aind-ephys-postprocessing capsule.

The fields below mirror the keys read from the capsule's ``params.json``
(https://github.com/AllenNeuralDynamics/aind-ephys-postprocessing/blob/main/code/params.json).
Each block has a ``to_dict`` returning the JSON fragment the capsule expects.
"""

from typing import Literal

from pydantic import Field, NonNegativeInt, PositiveFloat, PositiveInt

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


class PostprocessingJobKwargs(Block):
    """SpikeInterface job_kwargs for the postprocessing capsule."""

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

    def to_dict(self) -> dict:
        return {"chunk_duration": self.chunk_duration, "progress_bar": self.progress_bar}


class Sparsity(Block):
    """``sparsity`` parameters for the SortingAnalyzer."""

    method: Literal["radius", "best_channels", "snr", "ptp"] = Field(
        default="radius",
        title="Method",
        description="How to determine which channels are active for each unit.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    radius_um: PositiveFloat | list[PositiveFloat] = Field(
        default=100.0,
        title="Radius",
        description="Radius (μm) used by the 'radius' sparsity method.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )

    def to_dict(self) -> dict:
        return {"method": self.method, "radius_um": self.radius_um}


class RandomSpikes(Block):
    """``random_spikes`` extension parameters."""

    max_spikes_per_unit: PositiveInt | list[PositiveInt] = Field(
        default=500,
        title="Max spikes per unit",
        description="Cap on number of spikes selected per unit.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    method: Literal["uniform", "all"] = Field(
        default="uniform",
        title="Method",
        description="Spike-selection method.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    margin_size: PositiveInt | None = Field(
        default=None,
        title="Margin size",
        description="Margin in samples around segment boundaries.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    seed: NonNegativeInt | None = Field(
        default=None,
        title="Seed",
        description="Random seed (None for non-reproducible).",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    def to_dict(self) -> dict:
        return {
            "max_spikes_per_unit": self.max_spikes_per_unit,
            "method": self.method,
            "margin_size": self.margin_size,
            "seed": self.seed,
        }


class NoiseLevels(Block):
    """``noise_levels`` extension parameters."""

    num_chunks_per_segment: PositiveInt | list[PositiveInt] = Field(
        default=20,
        title="Num chunks per segment",
        description="Number of chunks sampled per segment.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    chunk_size: PositiveInt | list[PositiveInt] = Field(
        default=10000,
        title="Chunk size",
        description="Chunk size in samples.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    seed: NonNegativeInt | None = Field(
        default=None,
        title="Seed",
        description="Random seed (None for non-reproducible).",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    def to_dict(self) -> dict:
        return {
            "num_chunks_per_segment": self.num_chunks_per_segment,
            "chunk_size": self.chunk_size,
            "seed": self.seed,
        }


class Waveforms(Block):
    """``waveforms`` extension parameters."""

    ms_before: PositiveFloat | list[PositiveFloat] = Field(
        default=3.0,
        title="ms before",
        description="Window before each spike, in ms.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    ms_after: PositiveFloat | list[PositiveFloat] = Field(
        default=4.0,
        title="ms after",
        description="Window after each spike, in ms.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    dtype: str | None = Field(
        default=None,
        title="dtype",
        description="Force a specific dtype on the cached waveforms (None = auto).",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    def to_dict(self) -> dict:
        return {"ms_before": self.ms_before, "ms_after": self.ms_after, "dtype": self.dtype}


class SpikeAmplitudes(Block):
    """``spike_amplitudes`` extension parameters."""

    peak_sign: Literal["neg", "pos", "both"] = Field(
        default="neg",
        title="Peak sign",
        description="Direction of the peak.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )

    def to_dict(self) -> dict:
        return {"peak_sign": self.peak_sign}


class TemplateSimilarity(Block):
    """``template_similarity`` extension parameters."""

    method: Literal["l1", "l2", "cosine", "correlation"] = Field(
        default="l1",
        title="Method",
        description="Similarity metric.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )

    def to_dict(self) -> dict:
        return {"method": self.method}


class Correlograms(Block):
    """``correlograms`` extension parameters."""

    window_ms: PositiveFloat | list[PositiveFloat] = Field(
        default=50.0,
        title="Window",
        description="Correlogram window, in ms.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    bin_ms: PositiveFloat | list[PositiveFloat] = Field(
        default=1.0,
        title="Bin",
        description="Correlogram bin, in ms.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def to_dict(self) -> dict:
        return {"window_ms": self.window_ms, "bin_ms": self.bin_ms}


class IsiHistograms(Block):
    """``isi_histograms`` extension parameters."""

    window_ms: PositiveFloat | list[PositiveFloat] = Field(
        default=100.0,
        title="Window",
        description="ISI window, in ms.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    bin_ms: PositiveFloat | list[PositiveFloat] = Field(
        default=5.0,
        title="Bin",
        description="ISI bin, in ms.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def to_dict(self) -> dict:
        return {"window_ms": self.window_ms, "bin_ms": self.bin_ms}


class UnitLocations(Block):
    """``unit_locations`` extension parameters."""

    method: Literal[
        "monopolar_triangulation", "center_of_mass", "grid_convolution"
    ] = Field(
        default="monopolar_triangulation",
        title="Method",
        description="Unit-localization method.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )

    def to_dict(self) -> dict:
        return {"method": self.method}


class SpikeLocations(Block):
    """``spike_locations`` extension parameters."""

    method: Literal[
        "monopolar_triangulation", "center_of_mass", "grid_convolution"
    ] = Field(
        default="grid_convolution",
        title="Method",
        description="Spike-localization method.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )

    def to_dict(self) -> dict:
        return {"method": self.method}


class TemplateMetrics(Block):
    """``template_metrics`` extension parameters."""

    upsampling_factor: PositiveInt | list[PositiveInt] = Field(
        default=10,
        title="Upsampling factor",
        description="Temporal upsampling factor for template-metric computation.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    include_multi_channel_metrics: bool = Field(
        default=True,
        title="Multi-channel metrics",
        description="Compute multi-channel template metrics.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    def to_dict(self) -> dict:
        # Newer spikeinterface versions of ComputeTemplateMetrics dropped the
        # `sparsity` kwarg — we deliberately omit it here.
        return {
            "upsampling_factor": self.upsampling_factor,
            "include_multi_channel_metrics": self.include_multi_channel_metrics,
        }


class PrincipalComponents(Block):
    """``principal_components`` extension parameters."""

    n_components: PositiveInt | list[PositiveInt] = Field(
        default=5,
        title="n_components",
        description="Number of PCA components.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    mode: Literal["by_channel_local", "by_channel_global", "concatenated"] = Field(
        default="by_channel_local",
        title="Mode",
        description="PCA computation mode.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    whiten: bool = Field(
        default=True,
        title="Whiten",
        description="Whether to whiten the PCs.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    def to_dict(self) -> dict:
        return {
            "n_components": self.n_components,
            "mode": self.mode,
            "whiten": self.whiten,
        }


# Default upstream quality_metrics dict, reproduced verbatim except that
# `l_ratio` / `isolation_distance` are folded into `mahalanobis` (per newer
# spikeinterface) and the `nn_isolation` / `nn_noise_overlap` per-metric
# config blocks are kept in case the user adds those names back.
_DEFAULT_QUALITY_METRICS = {
    "presence_ratio": {"bin_duration_s": 60},
    "snr": {"peak_sign": "neg", "peak_mode": "extremum"},
    "isi_violation": {"isi_threshold_ms": 1.5, "min_isi_ms": 0},
    "rp_violation": {"refractory_period_ms": 1, "censored_period_ms": 0.0},
    "sliding_rp_violation": {
        "bin_size_ms": 0.25,
        "window_size_s": 1,
        "exclude_ref_period_below_ms": 0.5,
        "max_ref_period_ms": 10,
        "contamination_values": None,
    },
    "amplitude_cutoff": {
        "peak_sign": "neg",
        "num_histogram_bins": 100,
        "histogram_smoothing_value": 3,
        "amplitudes_bins_min_ratio": 5,
    },
    "amplitude_median": {"peak_sign": "neg"},
    "amplitude_cv": {
        "average_num_spikes_per_bin": 50,
        "percentiles": [5, 95],
        "min_num_bins": 10,
        "amplitude_extension": "spike_amplitudes",
    },
    "firing_range": {"bin_size_s": 5, "percentiles": [5, 95]},
    "synchrony": {"synchrony_sizes": [2, 4, 8]},
    "nearest_neighbor": {"max_spikes": 10000, "n_neighbors": 4},
    "nn_isolation": {
        "max_spikes": 10000,
        "min_spikes": 10,
        "n_neighbors": 4,
        "n_components": 10,
        "radius_um": 100,
    },
    "nn_noise_overlap": {
        "max_spikes": 10000,
        "min_spikes": 10,
        "n_neighbors": 4,
        "n_components": 10,
        "radius_um": 100,
    },
    "silhouette": {"method": ["simplified"]},
}

# Default metric names. Note: `l_ratio` and `isolation_distance` from upstream
# have been replaced by `mahalanobis` (newer spikeinterface re-organisation).
_DEFAULT_METRIC_NAMES: tuple[str, ...] = (
    "num_spikes",
    "firing_rate",
    "presence_ratio",
    "snr",
    "isi_violation",
    "rp_violation",
    "sliding_rp_violation",
    "amplitude_cutoff",
    "amplitude_median",
    "amplitude_cv",
    "synchrony",
    "firing_range",
    "drift",
    "mahalanobis",
    "d_prime",
    "nearest_neighbor",
    "silhouette",
)


class QualityMetrics(Block):
    """``quality_metrics_names`` + ``quality_metrics`` parameters.

    The capsule iterates the metric names in ``metric_names`` and looks up
    matching per-metric kwargs in the ``quality_metrics`` dict it ends up
    receiving. We expose the most-tuned per-metric knobs as flat fields and
    fold them into the default upstream dict via ``to_dict``.
    """

    metric_names: tuple[str, ...] = Field(
        default=_DEFAULT_METRIC_NAMES,
        title="Metric names",
        description="Names of quality metrics to compute.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    presence_ratio_bin_duration_s: PositiveFloat | list[PositiveFloat] = Field(
        default=60.0,
        title="Presence ratio bin duration",
        description="Bin duration (s) for presence_ratio.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.SECONDS,
        },
    )
    firing_range_bin_size_s: PositiveFloat | list[PositiveFloat] = Field(
        default=5.0,
        title="Firing range bin size",
        description="Bin size (s) for firing_range.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.SECONDS,
        },
    )
    amplitude_cv_min_num_bins: PositiveInt | list[PositiveInt] = Field(
        default=10,
        title="Amplitude CV min bins",
        description="Minimum number of amplitude bins for amplitude_cv.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    amplitude_cv_average_num_spikes_per_bin: PositiveInt | list[PositiveInt] = Field(
        default=50,
        title="Amplitude CV avg spikes/bin",
        description="Target spikes per bin for amplitude_cv.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    isi_threshold_ms: PositiveFloat | list[PositiveFloat] = Field(
        default=1.5,
        title="ISI threshold",
        description="ISI threshold (ms) for isi_violation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def to_dict(self) -> dict:
        """Return the per-metric kwargs dict, applying overrides to defaults.

        Only retains entries for metric names that are actually requested,
        so the capsule's ``ComputeQualityMetrics._set_params`` doesn't fail
        on unknown / removed metrics (e.g. ``nn_isolation`` was deprecated).
        """
        cfg: dict = {k: dict(v) for k, v in _DEFAULT_QUALITY_METRICS.items()}
        cfg.setdefault("presence_ratio", {})["bin_duration_s"] = (
            self.presence_ratio_bin_duration_s
        )
        cfg.setdefault("firing_range", {})["bin_size_s"] = self.firing_range_bin_size_s
        cfg.setdefault("amplitude_cv", {})["min_num_bins"] = self.amplitude_cv_min_num_bins
        cfg.setdefault("amplitude_cv", {})["average_num_spikes_per_bin"] = (
            self.amplitude_cv_average_num_spikes_per_bin
        )
        cfg.setdefault("isi_violation", {})["isi_threshold_ms"] = self.isi_threshold_ms

        keep = set(self.metric_names)
        return {k: v for k, v in cfg.items() if k in keep}
