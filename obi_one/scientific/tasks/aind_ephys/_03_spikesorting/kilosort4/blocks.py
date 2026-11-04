"""Kilosort4's parameters, by theme.

See ``kilosort.parameters`` for the meaning of each. Defaults are those of the AIND pipeline's
``default_params.json``.
"""

from typing import Literal

from pydantic import Field, NonNegativeFloat, NonNegativeInt, PositiveFloat, PositiveInt

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.blocks import SorterParameters


class Kilosort4Preprocessing(SorterParameters):
    """How Kilosort batches, filters, references and whitens the recording."""

    do_CAR: bool = Field(  # ruff: ignore[mixed-case-variable-in-class-scope]
        default=True,
        title="Do CAR",
        description="Apply common-average referencing inside Kilosort.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    invert_sign: bool = Field(
        default=False,
        title="Invert sign",
        description="Invert the sign of the recording.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    shift: float | None = Field(
        default=None,
        title="Shift",
        description="Manual shift applied to the recording.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL},
    )
    scale: float | None = Field(
        default=None,
        title="Scale",
        description="Manual scale applied to the recording.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL},
    )
    artifact_threshold: float | None = Field(
        default=None,
        title="Artifact threshold",
        description="Reject any batch whose abs amplitude exceeds this value.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL},
    )
    highpass_cutoff: PositiveFloat | list[PositiveFloat] = Field(
        default=300.0,
        title="Highpass cutoff",
        description="Highpass cutoff used by Kilosort's internal preprocessing.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )
    nskip: PositiveInt | list[PositiveInt] = Field(
        default=25,
        title="Whitening nskip",
        description="Stride between batches used to estimate whitening.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    whitening_range: PositiveInt | list[PositiveInt] = Field(
        default=32,
        title="Whitening range",
        description="Number of channels per whitening neighbourhood.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    batch_size: PositiveInt | list[PositiveInt] = Field(
        default=60000,
        title="Batch size",
        description="Number of samples per batch (default 60000 ≈ 2 s @ 30 kHz).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    batch_downsampling: PositiveInt | list[PositiveInt] = Field(
        default=1,
        title="Batch downsampling",
        description=(
            "Sort only every n-th batch. 1 uses all of them, which is what Kilosort recommends."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    bad_channels: tuple[int, ...] | None = Field(
        default=None,
        title="Bad channels",
        description="Explicit list of bad channel indices.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_LIST_OPTIONAL},
    )
    skip_kilosort_preprocessing: bool = Field(
        default=False,
        title="Skip Kilosort preprocessing",
        description="Skip Kilosort's internal preprocessing (filter + whitening).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )


class Kilosort4DriftCorrection(SorterParameters):
    """Kilosort's own drift correction."""

    do_correction: bool = Field(
        default=True,
        title="Do correction",
        description="Whether Kilosort should run its own drift correction.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    nblocks: NonNegativeInt | list[NonNegativeInt] = Field(
        default=5,
        title="Drift blocks",
        description="Number of probe blocks for drift correction (0 = rigid only).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    binning_depth: PositiveFloat | list[PositiveFloat] = Field(
        default=5.0,
        title="Binning depth",
        description="Depth bin size for drift estimation, in microns.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    sig_interp: PositiveFloat | list[PositiveFloat] = Field(
        default=20.0,
        title="Sig interp",
        description="Spatial smoothing sigma for drift interpolation.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    drift_smoothing_correlation: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.5,
        title="Drift smoothing: correlation",
        description=(
            "Gaussian smoothing of the drift estimate along the correlation axis. "
            "Changing it is not recommended."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    drift_smoothing_time: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.5,
        title="Drift smoothing: time",
        description=("Gaussian smoothing of the drift estimate over time, in registration blocks."),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    drift_smoothing_depth: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.5,
        title="Drift smoothing: depth",
        description=(
            "Gaussian smoothing of the drift estimate over depth, in batches. No "
            "effect with one drift block."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    def to_dict(self) -> dict:
        parameters = super().to_dict()
        parameters["drift_smoothing"] = (
            parameters.pop("drift_smoothing_correlation"),
            parameters.pop("drift_smoothing_time"),
            parameters.pop("drift_smoothing_depth"),
        )
        return parameters


class Kilosort4SpikeDetection(SorterParameters):
    """Detection thresholds."""

    Th_universal: float | list[float] = Field(
        default=9.0,
        title="Th universal",
        description="Universal-template detection threshold.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    Th_learned: float | list[float] = Field(
        default=8.0,
        title="Th learned",
        description="Learned-template detection threshold.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    Th_single_ch: float | list[float] = Field(
        default=6.0,
        title="Th single ch",
        description="Single-channel detection threshold.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    max_peels: PositiveInt | list[PositiveInt] = Field(
        default=100,
        title="Matching iterations",
        description=(
            "Passes over each batch in the matching pursuit. More can detect more "
            "overlapping spikes."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )


class Kilosort4Templates(SorterParameters):
    """The shape and spatial grid of the templates."""

    nt: PositiveInt | list[PositiveInt] = Field(
        default=61,
        title="Template length",
        description="Number of samples per template (must be odd).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    nt0min: int | None = Field(
        default=None,
        title="Waveform alignment sample",
        description="Minimum sample to align spikes (defaults to nt // 2).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_OPTIONAL},
    )
    dmin: float | None = Field(
        default=None,
        title="Vertical template spacing",
        description="Distance bin size for templates (auto if None).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL},
    )
    dminx: PositiveFloat | list[PositiveFloat] = Field(
        default=32.0,
        title="dminx",
        description="Lateral distance bin size for templates.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    x_centers: int | None = Field(
        default=None,
        title="Lateral grid centers",
        description="Number of x-centres for template grid (auto if None).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_OPTIONAL},
    )
    min_template_size: PositiveFloat | list[PositiveFloat] = Field(
        default=10.0,
        title="Min template size",
        description="Minimum spatial extent of templates (microns).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    template_sizes: PositiveInt | list[PositiveInt] = Field(
        default=5,
        title="Template sizes",
        description="Number of template sizes to try.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    nearest_chans: PositiveInt | list[PositiveInt] = Field(
        default=10,
        title="Nearest channels",
        description="Number of nearest channels considered per template.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    nearest_templates: PositiveInt | list[PositiveInt] = Field(
        default=100,
        title="Nearest templates",
        description="Number of nearest templates considered per spike.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    max_channel_distance: PositiveFloat | None = Field(
        default=None,
        title="Max channel distance",
        description="Max distance from extremum channel to consider, microns.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_OPTIONAL,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    templates_from_data: bool = Field(
        default=True,
        title="Templates from data",
        description="Initialise templates from the data (vs from a fixed bank).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    n_templates: PositiveInt | list[PositiveInt] = Field(
        default=6,
        title="n_templates",
        description="Number of templates per cluster during template fitting.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    n_pcs: PositiveInt | list[PositiveInt] = Field(
        default=6,
        title="n_pcs",
        description="Number of principal components retained per template.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    position_limit: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=100.0,
        title="Position estimate limit",
        description=(
            "Farthest channel used to estimate spike positions after sorting. Sorting"
            " is unaffected."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )


class Kilosort4Clustering(SorterParameters):
    """Splitting and merging clusters, and which of them to keep."""

    acg_threshold: float | list[float] = Field(
        default=0.2,
        title="ACG threshold",
        description="Auto-correlogram threshold for cluster splitting.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    ccg_threshold: float | list[float] = Field(
        default=0.25,
        title="CCG threshold",
        description="Cross-correlogram threshold for cluster merging.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    cluster_downsampling: PositiveInt | list[PositiveInt] = Field(
        default=20,
        title="Cluster downsampling",
        description="Downsampling factor used during clustering.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    duplicate_spike_ms: PositiveFloat | list[PositiveFloat] = Field(
        default=0.25,
        title="Duplicate spike ms",
        description="Window in ms for marking duplicate spikes.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    keep_good_only: bool = Field(
        default=False,
        title="Keep good only",
        description="Only keep clusters labelled 'good' by Kilosort.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    cluster_neighbors: PositiveInt | list[PositiveInt] = Field(
        default=10,
        title="Cluster neighbors",
        description="Nearest spike neighbors searched when building the clustering graph.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    max_cluster_subset: PositiveInt | list[PositiveInt] = Field(
        default=25000,
        title="Maximum cluster subset",
        description="Most spikes searched for neighbors when building the clustering graph.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    cluster_init_seed: PositiveInt | list[PositiveInt] = Field(
        default=5,
        title="Clustering seed",
        description="Random seed of the k-means++ initialization of the clustering graph.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )


class Kilosort4Runtime(SorterParameters):
    """Execution settings the platform defines: the device and what Kilosort keeps on disk."""

    torch_device: Literal["auto", "cpu", "cuda", "mps"] = Field(
        default="auto",
        title="Torch device",
        description="Torch device ('auto' picks CUDA if available).",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    clear_cache: bool = Field(
        default=False,
        title="Clear cache",
        description="Clear PyTorch GPU cache between sub-steps.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    save_preprocessed_copy: bool = Field(
        default=False,
        title="Save preprocessed copy",
        description="Save Kilosort's internal preprocessed binary alongside the sorting.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    save_extra_vars: bool = Field(
        default=False,
        title="Save extra vars",
        description="Save extra variables for debugging.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    use_binary_file: bool | None = Field(
        default=None,
        title="Use binary file",
        description="Force binary-file IO (None = auto).",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    delete_recording_dat: bool = Field(
        default=True,
        title="Delete recording dat",
        description="Delete Kilosort's intermediate .dat after sorting.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
