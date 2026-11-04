"""Blocks for the postprocessing stage of the AIND ephys pipeline.

Each block's ``to_dict`` gives the parameters of one ``SortingAnalyzer`` extension. Defaults are
those of the AIND pipeline's ``default_params.json``.
"""

from typing import Literal

from pydantic import Field, NonNegativeFloat, NonNegativeInt, PositiveFloat, PositiveInt

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units

DEFAULT_QUALITY_METRIC_NAMES = (
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
    "noise_cutoff",
    "synchrony",
    "firing_range",
    "drift",
    "sd_ratio",
    "mahalanobis",
    "d_prime",
    "nearest_neighbor",
    "silhouette",
)


class Sparsity(Block):
    """Which channels each unit's waveforms are kept on."""

    method: Literal["radius", "best_channels", "closest_channels", "snr", "amplitude"] = Field(
        default="radius",
        title="Sparsity method",
        description="How each unit's channels are chosen.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    radius_um: PositiveFloat | list[PositiveFloat] = Field(
        default=100.0,
        title="Radius",
        description="Radius around each unit's main channel, for the 'radius' method.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )

    def to_dict(self) -> dict:
        return {"method": self.method, "radius_um": self.radius_um}


class RandomSpikes(Block):
    """``random_spikes``: the spikes waveforms are extracted for."""

    max_spikes_per_unit: PositiveInt | list[PositiveInt] = Field(
        default=500,
        title="Max spikes per unit",
        description="Number of spikes sampled per unit.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    method: Literal["uniform", "all"] = Field(
        default="uniform",
        title="Sampling method",
        description="How the spikes are sampled.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    seed: NonNegativeInt | None = Field(
        default=None,
        title="Random seed",
        description="Seed of the sampling. None draws one.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    def to_dict(self) -> dict:
        return {
            "max_spikes_per_unit": self.max_spikes_per_unit,
            "method": self.method,
            "margin_size": None,
            "seed": self.seed,
        }


class NoiseLevels(Block):
    """``noise_levels``, estimated from random chunks."""

    num_chunks_per_segment: PositiveInt | list[PositiveInt] = Field(
        default=20,
        title="Chunks per segment",
        description="Number of random chunks per segment.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    chunk_size: PositiveInt | list[PositiveInt] = Field(
        default=10_000,
        title="Chunk size",
        description="Number of samples per chunk.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    seed: NonNegativeInt | None = Field(
        default=None,
        title="Random seed",
        description="Seed of the chunk choice. None draws one.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    def to_dict(self) -> dict:
        return {
            "random_slices_kwargs": {
                "num_chunks_per_segment": self.num_chunks_per_segment,
                "chunk_size": self.chunk_size,
                "seed": self.seed,
            }
        }


class Waveforms(Block):
    """``waveforms``: the window cut around each sampled spike."""

    ms_before: PositiveFloat | list[PositiveFloat] = Field(
        default=2.0,
        title="Before",
        description="Window before each spike.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    ms_after: PositiveFloat | list[PositiveFloat] = Field(
        default=3.0,
        title="After",
        description="Window after each spike.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def to_dict(self) -> dict:
        return {"ms_before": self.ms_before, "ms_after": self.ms_after, "dtype": None}


class TemplateSimilarity(Block):
    """``template_similarity`` between units."""

    method: Literal["l1", "l2", "cosine"] = Field(
        default="l1",
        title="Similarity method",
        description="How template similarity is measured.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )

    def to_dict(self) -> dict:
        return {"method": self.method}


class Correlograms(Block):
    """``correlograms`` between units."""

    window_ms: PositiveFloat | list[PositiveFloat] = Field(
        default=50.0,
        title="Window",
        description="Correlogram window.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    bin_ms: PositiveFloat | list[PositiveFloat] = Field(
        default=1.0,
        title="Bin",
        description="Correlogram bin.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def to_dict(self) -> dict:
        return {"window_ms": self.window_ms, "bin_ms": self.bin_ms}


class IsiHistograms(Block):
    """``isi_histograms`` of each unit."""

    window_ms: PositiveFloat | list[PositiveFloat] = Field(
        default=100.0,
        title="Window",
        description="Histogram window.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    bin_ms: PositiveFloat | list[PositiveFloat] = Field(
        default=5.0,
        title="Bin",
        description="Histogram bin.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def to_dict(self) -> dict:
        return {"window_ms": self.window_ms, "bin_ms": self.bin_ms}


class UnitLocations(Block):
    """``unit_locations``."""

    method: Literal["monopolar_triangulation", "center_of_mass", "grid_convolution"] = Field(
        default="monopolar_triangulation",
        title="Localization method",
        description="How each unit is localized.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )

    def to_dict(self) -> dict:
        return {"method": self.method}


class SpikeLocations(Block):
    """``spike_locations``."""

    method: Literal["grid_convolution", "center_of_mass", "monopolar_triangulation"] = Field(
        default="grid_convolution",
        title="Localization method",
        description="How each spike is localized.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )

    def to_dict(self) -> dict:
        return {"method": self.method}


class TemplateMetrics(Block):
    """``template_metrics`` of each unit's template."""

    upsampling_factor: PositiveInt | list[PositiveInt] = Field(
        default=10,
        title="Upsampling factor",
        description="Upsampling of the templates before the metrics are measured.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    include_multi_channel_metrics: bool = Field(
        default=True,
        title="Multi-channel metrics",
        description="Whether to include the metrics that span several channels.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    def to_dict(self) -> dict:
        return {
            "upsampling_factor": self.upsampling_factor,
            "include_multi_channel_metrics": self.include_multi_channel_metrics,
        }


class PrincipalComponents(Block):
    """``principal_components`` of the waveforms, used by the PCA quality metrics."""

    n_components: PositiveInt | list[PositiveInt] = Field(
        default=5,
        title="Components",
        description="Number of principal components.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    mode: Literal["by_channel_local", "by_channel_global", "concatenated"] = Field(
        default="by_channel_local",
        title="Mode",
        description="Whether components are fitted per channel and unit, per channel, or jointly.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    whiten: bool = Field(
        default=True,
        title="Whiten",
        description="Whether to whiten the components.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    def to_dict(self) -> dict:
        return {"n_components": self.n_components, "mode": self.mode, "whiten": self.whiten}


class QualityMetrics(Block):
    """``quality_metrics``, with the parameters the AIND pipeline sets for each metric."""

    metric_names: tuple[str, ...] = Field(
        default=DEFAULT_QUALITY_METRIC_NAMES,
        title="Metrics",
        description="Quality metrics to compute.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    presence_ratio_bin_duration_s: PositiveFloat | list[PositiveFloat] = Field(
        default=60.0,
        title="Presence ratio bin",
        description="Bin of the presence ratio.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.SECONDS,
        },
    )
    snr_method: Literal["extremum", "peak_to_peak"] = Field(
        default="extremum",
        title="SNR method",
        description="Which amplitude the SNR divides by the noise.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    isi_threshold_ms: PositiveFloat | list[PositiveFloat] = Field(
        default=1.5,
        title="ISI threshold",
        description="Inter-spike intervals below this are violations.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    min_isi_ms: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        title="Minimum ISI",
        description="Shortest possible inter-spike interval (duplicates removed by sorting).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    refractory_period_ms: PositiveFloat | list[PositiveFloat] = Field(
        default=1.0,
        title="Refractory period",
        description="Refractory period of the refractory-period violation metric.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    censored_period_ms: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        title="Censored period",
        description="Censored period of the refractory-period violation metric.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    amplitude_cv_average_num_spikes_per_bin: PositiveInt | list[PositiveInt] = Field(
        default=50,
        title="Amplitude CV spikes per bin",
        description="Average number of spikes per bin of the amplitude CV.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    amplitude_cv_min_num_bins: PositiveInt | list[PositiveInt] = Field(
        default=10,
        title="Amplitude CV minimum bins",
        description="Fewest bins the amplitude CV is computed over.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    sd_ratio_censored_period_ms: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=4.0,
        title="SD ratio censored period",
        description="Censored period of the standard-deviation ratio.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    firing_range_bin_size_s: PositiveFloat | list[PositiveFloat] = Field(
        default=5.0,
        title="Firing range bin",
        description="Bin of the firing range.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.SECONDS,
        },
    )
    nearest_neighbor_max_spikes: PositiveInt | list[PositiveInt] = Field(
        default=10_000,
        title="Nearest-neighbour spikes",
        description="Spikes sampled for the nearest-neighbour metrics.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    nearest_neighbor_n_neighbors: PositiveInt | list[PositiveInt] = Field(
        default=5,
        title="Nearest neighbours",
        description="Number of neighbours of the nearest-neighbour metrics.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    def to_dict(self) -> dict:
        return {
            "metric_names": list(self.metric_names),
            "metric_params": {
                "presence_ratio": {"bin_duration_s": self.presence_ratio_bin_duration_s},
                "snr": {"method": self.snr_method},
                "isi_violation": {
                    "isi_threshold_ms": self.isi_threshold_ms,
                    "min_isi_ms": self.min_isi_ms,
                },
                "rp_violation": {
                    "refractory_period_ms": self.refractory_period_ms,
                    "censored_period_ms": self.censored_period_ms,
                },
                "sliding_rp_violation": {
                    "bin_size_ms": 0.25,
                    "window_size_s": 1,
                    "exclude_ref_period_below_ms": 0.5,
                    "max_ref_period_ms": 10,
                    "contamination_values": None,
                },
                "amplitude_cutoff": {
                    "num_histogram_bins": 100,
                    "histogram_smoothing_value": 3,
                    "amplitudes_bins_min_ratio": 5,
                },
                "amplitude_cv": {
                    "average_num_spikes_per_bin": self.amplitude_cv_average_num_spikes_per_bin,
                    "percentiles": [5, 95],
                    "min_num_bins": self.amplitude_cv_min_num_bins,
                    "amplitude_extension": "spike_amplitudes",
                },
                "noise_cutoff": {"high_quantile": 0.25, "low_quantile": 0.1, "n_bins": 100},
                "sd_ratio": {
                    "censored_period_ms": self.sd_ratio_censored_period_ms,
                    "correct_for_drift": True,
                    "correct_for_template_itself": True,
                },
                "firing_range": {
                    "bin_size_s": self.firing_range_bin_size_s,
                    "percentiles": [5, 95],
                },
                "nearest_neighbor": {
                    "max_spikes": self.nearest_neighbor_max_spikes,
                    "n_neighbors": self.nearest_neighbor_n_neighbors,
                },
                "silhouette": {"method": ["simplified"]},
            },
        }
