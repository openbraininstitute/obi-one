"""Building blocks for the aind-ephys-visualization capsule.

Mirrors the keys read from the capsule's ``params.json``
(https://github.com/AllenNeuralDynamics/aind-ephys-visualization/blob/main/code/params.json).
"""

from typing import Literal

from pydantic import Field, NonNegativeInt, PositiveFloat, PositiveInt

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


class VisualizationJobKwargs(Block):
    """SpikeInterface job_kwargs for the visualization capsule."""

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


class TimeseriesViz(Block):
    """``timeseries`` parameters."""

    n_snippets_per_segment: PositiveInt | list[PositiveInt] = Field(
        default=2,
        title="Snippets per segment",
        description="Number of trace snippets emitted per segment.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    snippet_duration_s: PositiveFloat | list[PositiveFloat] = Field(
        default=0.5,
        title="Snippet duration",
        description="Length of each trace snippet in seconds.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.SECONDS,
        },
    )

    def to_dict(self) -> dict:
        return {
            "n_snippets_per_segment": self.n_snippets_per_segment,
            "snippet_duration_s": self.snippet_duration_s,
        }


class DriftViz(Block):
    """``drift`` parameters for the drift-map figure."""

    peak_sign: Literal["neg", "pos", "both"] = Field(
        default="neg",
        title="Peak sign",
        description="Direction of detected peaks.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    detect_threshold: PositiveFloat | list[PositiveFloat] = Field(
        default=5.0,
        title="Detect threshold",
        description="Threshold for peak detection.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    exclude_sweep_ms: PositiveFloat | list[PositiveFloat] = Field(
        default=0.1,
        title="Exclude sweep",
        description="Refractory window for peak detection (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    localization_ms_before: PositiveFloat | list[PositiveFloat] = Field(
        default=0.1,
        title="Localization ms before",
        description="Window before each peak for localization (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    localization_ms_after: PositiveFloat | list[PositiveFloat] = Field(
        default=0.3,
        title="Localization ms after",
        description="Window after each peak for localization (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    localization_radius_um: PositiveFloat | list[PositiveFloat] = Field(
        default=100.0,
        title="Localization radius",
        description="Channel-neighbourhood radius for localization, μm.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    n_skip: PositiveInt | list[PositiveInt] = Field(
        default=30,
        title="n_skip",
        description="Subsampling factor for the drift map.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    alpha: PositiveFloat | list[PositiveFloat] = Field(
        default=0.15,
        title="Alpha",
        description="Plot transparency.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    vmin: float | list[float] = Field(
        default=-200.0,
        title="vmin",
        description="Lower colour-map bound (μV).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    vmax: float | list[float] = Field(
        default=0.0,
        title="vmax",
        description="Upper colour-map bound (μV).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    cmap: str = Field(
        default="Greys_r",
        title="Colormap",
        description="Matplotlib colormap.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    figsize: tuple[float, float] = Field(
        default=(10.0, 10.0),
        title="figsize",
        description="Matplotlib figure size (inches).",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    def to_dict(self) -> dict:
        return {
            "detection": {
                "peak_sign": self.peak_sign,
                "detect_threshold": self.detect_threshold,
                "exclude_sweep_ms": self.exclude_sweep_ms,
            },
            "localization": {
                "ms_before": self.localization_ms_before,
                "ms_after": self.localization_ms_after,
                "radius_um": self.localization_radius_um,
            },
            "n_skip": self.n_skip,
            "alpha": self.alpha,
            "vmin": self.vmin,
            "vmax": self.vmax,
            "cmap": self.cmap,
            "figsize": list(self.figsize),
        }


class MotionViz(Block):
    """``motion`` parameters for the motion-correction figure."""

    cmap: str = Field(
        default="Greys_r",
        title="Colormap",
        description="Matplotlib colormap.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    scatter_decimate: NonNegativeInt | list[NonNegativeInt] = Field(
        default=15,
        title="Scatter decimate",
        description="Decimation factor for the motion scatter plot.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    figsize: tuple[float, float] = Field(
        default=(15.0, 10.0),
        title="figsize",
        description="Matplotlib figure size (inches).",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    def to_dict(self) -> dict:
        return {
            "cmap": self.cmap,
            "scatter_decimate": self.scatter_decimate,
            "figsize": list(self.figsize),
        }
