"""Building blocks for the aind-ephys-spikesort-kilosort4 capsule.

The fields below mirror the keys read from the capsule's ``params.json``
(https://github.com/AllenNeuralDynamics/aind-ephys-spikesort-kilosort4/blob/main/code/params.json).
Each block has a ``to_dict`` returning the JSON fragment the capsule expects
for that section.
"""

from typing import Literal

from pydantic import Field, NonNegativeInt, PositiveFloat, PositiveInt

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


class Kilosort4JobKwargs(Block):
    """SpikeInterface job_kwargs for the Kilosort4 capsule."""

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


class Kilosort4Sorter(Block):
    """Kilosort4 sorter parameters (the ``sorter`` section of params.json).

    See `kilosort.run_kilosort.default_settings` and the upstream
    `params.json` for the meaning of every flag.
    """

    # --- Universal / batching -------------------------------------------------
    batch_size: PositiveInt | list[PositiveInt] = Field(
        default=60000,
        title="Batch size",
        description="Number of samples per batch (default 60000 ≈ 2 s @ 30 kHz).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    nblocks: NonNegativeInt | list[NonNegativeInt] = Field(
        default=5,
        title="Drift blocks",
        description="Number of probe blocks for drift correction (0 = rigid only).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
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
    do_CAR: bool = Field(
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
    nt: PositiveInt | list[PositiveInt] = Field(
        default=61,
        title="Template length",
        description="Number of samples per template (must be odd).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    shift: float | None = Field(
        default=None,
        title="Shift",
        description="Manual shift applied to the recording.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    scale: float | None = Field(
        default=None,
        title="Scale",
        description="Manual scale applied to the recording.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    artifact_threshold: float | None = Field(
        default=None,
        title="Artifact threshold",
        description="Reject any batch whose abs amplitude exceeds this value.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    # --- Whitening ------------------------------------------------------------
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

    # --- Filtering ------------------------------------------------------------
    highpass_cutoff: PositiveFloat | list[PositiveFloat] = Field(
        default=300.0,
        title="Highpass cutoff",
        description="Highpass cutoff used by Kilosort's internal preprocessing.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )

    # --- Drift ----------------------------------------------------------------
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
    drift_smoothing: tuple[float, float, float] = Field(
        default=(0.5, 0.5, 0.5),
        title="Drift smoothing",
        description="Sigma values for drift smoothing along (time, x, y).",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    # --- Templates ------------------------------------------------------------
    nt0min: int | None = Field(
        default=None,
        title="nt0min",
        description="Minimum sample to align spikes (defaults to nt // 2).",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    dmin: float | None = Field(
        default=None,
        title="dmin",
        description="Distance bin size for templates (auto if None).",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    dminx: PositiveFloat | list[PositiveFloat] = Field(
        default=32.0,
        title="dminx",
        description="Lateral distance bin size for templates.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
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
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    # --- Template generation --------------------------------------------------
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
    Th_single_ch: float | list[float] = Field(
        default=6.0,
        title="Th single ch",
        description="Single-channel detection threshold.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    # --- Clustering -----------------------------------------------------------
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
    x_centers: int | None = Field(
        default=None,
        title="x_centers",
        description="Number of x-centres for template grid (auto if None).",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
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

    # --- Runtime / IO ---------------------------------------------------------
    save_preprocessed_copy: bool = Field(
        default=False,
        title="Save preprocessed copy",
        description="Save Kilosort's internal preprocessed binary alongside the sorting.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    torch_device: Literal["auto", "cpu", "cuda", "mps"] = Field(
        default="auto",
        title="Torch device",
        description="Torch device ('auto' picks CUDA if available).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    bad_channels: tuple[int, ...] | None = Field(
        default=None,
        title="Bad channels",
        description="Explicit list of bad channel indices.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    clear_cache: bool = Field(
        default=False,
        title="Clear cache",
        description="Clear PyTorch GPU cache between sub-steps.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    save_extra_vars: bool = Field(
        default=False,
        title="Save extra vars",
        description="Save extra variables for debugging.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    do_correction: bool = Field(
        default=True,
        title="Do correction",
        description="Whether Kilosort should run its own drift correction.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    keep_good_only: bool = Field(
        default=False,
        title="Keep good only",
        description="Only keep clusters labelled 'good' by Kilosort.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    skip_kilosort_preprocessing: bool = Field(
        default=False,
        title="Skip Kilosort preprocessing",
        description="Skip Kilosort's internal preprocessing (filter + whitening).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
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
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    def to_dict(self) -> dict:
        """Serialise to the dict expected under the params.json ``sorter`` key."""
        return {
            "batch_size": self.batch_size,
            "nblocks": self.nblocks,
            "Th_universal": self.Th_universal,
            "Th_learned": self.Th_learned,
            "do_CAR": self.do_CAR,
            "invert_sign": self.invert_sign,
            "nt": self.nt,
            "shift": self.shift,
            "scale": self.scale,
            "artifact_threshold": self.artifact_threshold,
            "nskip": self.nskip,
            "whitening_range": self.whitening_range,
            "highpass_cutoff": self.highpass_cutoff,
            "binning_depth": self.binning_depth,
            "sig_interp": self.sig_interp,
            "drift_smoothing": self.drift_smoothing,
            "nt0min": self.nt0min,
            "dmin": self.dmin,
            "dminx": self.dminx,
            "min_template_size": self.min_template_size,
            "template_sizes": self.template_sizes,
            "nearest_chans": self.nearest_chans,
            "nearest_templates": self.nearest_templates,
            "max_channel_distance": self.max_channel_distance,
            "templates_from_data": self.templates_from_data,
            "n_templates": self.n_templates,
            "n_pcs": self.n_pcs,
            "Th_single_ch": self.Th_single_ch,
            "acg_threshold": self.acg_threshold,
            "ccg_threshold": self.ccg_threshold,
            "cluster_downsampling": self.cluster_downsampling,
            "x_centers": self.x_centers,
            "duplicate_spike_ms": self.duplicate_spike_ms,
            "save_preprocessed_copy": self.save_preprocessed_copy,
            "torch_device": self.torch_device,
            "bad_channels": self.bad_channels,
            "clear_cache": self.clear_cache,
            "save_extra_vars": self.save_extra_vars,
            "do_correction": self.do_correction,
            "keep_good_only": self.keep_good_only,
            "skip_kilosort_preprocessing": self.skip_kilosort_preprocessing,
            "use_binary_file": self.use_binary_file,
            "delete_recording_dat": self.delete_recording_dat,
        }
