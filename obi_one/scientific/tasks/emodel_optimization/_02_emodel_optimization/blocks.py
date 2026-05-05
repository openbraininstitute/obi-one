"""Blocks for the 01_emodel_optimization stage."""

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, NonNegativeInt, PositiveFloat, PositiveInt

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


class OptimizationInitialize(Block):
    """Filesystem inputs for the optimisation stage."""

    previous_stage_output_path: Path = Field(
        title="Previous stage output path",
        description=(
            "Path to the working directory produced by the 00_efeature_extraction stage"
            " (typically ``obi-output/00_efeature_extraction/grid_scan/0/``). The stage"
            " copies ``config/``, ``morphologies/``, ``mechanisms/``, the compiled"
            " ``x86_64``/``arm64`` directory, and ``ephys_data/`` from this path."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    emodel: str = Field(
        title="E-Model name",
        description="Top-level key in ``recipes.json`` to operate on (must match stage 00).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    species: str = Field(
        default="rat",
        title="Species",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    brain_region: str = Field(
        default="SSCX",
        title="Brain region",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    etype: str | None = Field(default=None, json_schema_extra={SchemaKey.UI_HIDDEN: True})
    mtype: str | None = Field(default=None, json_schema_extra={SchemaKey.UI_HIDDEN: True})
    ttype: str | None = Field(default=None, json_schema_extra={SchemaKey.UI_HIDDEN: True})

    iteration_tag: str | None = Field(
        default=None,
        title="Iteration tag",
        description=(
            "BluePyEModel ``iteration_tag`` (also called ``githash``) used to namespace"
            " checkpoints under ``./run/<tag>/``."
        ),
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    use_multiprocessing: bool = Field(
        default=False,
        title="Use multiprocessing",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    use_ipyparallel: bool = Field(
        default=False,
        title="Use ipyparallel",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )


class OptimizationParams(Block):
    """``optimisation_params`` block (passed verbatim to BluePyEModel)."""

    offspring_size: PositiveInt | list[PositiveInt] = Field(
        default=4,
        title="Offspring size",
        description=(
            "Population size per generation. The L5PC example uses 20; we default"
            " to a small value so the bundled example completes quickly."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    def to_dict(self) -> dict:
        return {"offspring_size": self.offspring_size}


class OptimizationSettings(Block):
    """Top-level ``pipeline_settings`` keys controlling optimisation."""

    optimiser: Literal["CMA_ES", "MO-CMA", "IBEA", "SO-CMA"] = Field(
        default="CMA_ES",
        title="Optimiser",
        description=(
            "BluePyEModel optimiser. ``CMA_ES`` is the single-objective Covariance"
            " Matrix Adaptation Evolution Strategy; the L5PC example uses ``MO-CMA``."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    max_ngen: PositiveInt | list[PositiveInt] = Field(
        default=2,
        title="Max generations",
        description=(
            "Generation cap for the optimiser. The L5PC example uses 100; we default"
            " to a very small value so the bundled example completes quickly."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    optimisation_timeout: PositiveFloat | list[PositiveFloat] = Field(
        default=300.0,
        title="Optimisation timeout",
        description="Hard wall-clock limit per optimisation run.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.SECONDS,
        },
    )
    validation_threshold: PositiveFloat | list[PositiveFloat] = Field(
        default=5.0,
        title="Validation threshold",
        description="Z-score threshold below which a model is considered validated.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    seed: NonNegativeInt | list[NonNegativeInt] = Field(
        default=1,
        title="Random seed",
        description="Seed forwarded to ``pipeline.optimise(seed=...)``.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    def to_dict(self, optimisation_params: OptimizationParams) -> dict[str, Any]:
        return {
            "optimiser": self.optimiser,
            "max_ngen": self.max_ngen,
            "optimisation_timeout": self.optimisation_timeout,
            "validation_threshold": self.validation_threshold,
            "optimisation_params": optimisation_params.to_dict(),
        }
