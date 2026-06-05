"""Blocks for the 02_emodel_optimization stage."""

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
            "Path to the working directory produced by the 01_efeature_extraction stage"
            " (typically ``obi-output/01_efeature_extraction/grid_scan/0/``). The stage"
            " copies ``ephys_data/`` and the ``extracted_features.json`` file from this"
            " path; everything else is supplied below."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    recipes_path: Path = Field(
        title="Recipes JSON path",
        description=(
            "Path to a BluePyEModel ``recipes.json`` file. Copied to"
            " ``./config/recipes.json`` after the optimisation-related"
            " ``pipeline_settings`` overrides have been merged in. The extracted"
            " features from the previous stage are written into the path indicated"
            " by ``recipes[<emodel>]['features']``."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    morphology_path: Path = Field(
        title="Morphologies path",
        description=(
            "Directory containing the morphology asc/swc/h5 files referenced from the"
            " recipe. Copied into the working directory at ``./morphologies/``."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    mechanisms_path: Path = Field(
        title="Mechanisms path",
        description=(
            "Directory containing the NEURON ``.mod`` files. Copied to ``./mechanisms/``"
            " and compiled via ``nrnivmodl``."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    params_path: Path = Field(
        title="Parameters JSON path",
        description=(
            "Path to the BluePyEModel parameters file (e.g. ``config/params/pyr.json``)."
            " Copied to ``./config/params/<basename>``; the path inside ``recipes.json``"
            " is preserved."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    emodel: str = Field(
        title="E-Model name",
        description="Top-level key in ``recipes.json`` to operate on (e.g. ``L5PC``).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    species: str = Field(
        default="rat",
        title="Species",
        description="Species tag passed to ``EModel_pipeline``.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    brain_region: str = Field(
        default="SSCX",
        title="Brain region",
        description="Brain region tag passed to ``EModel_pipeline``.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    etype: str | None = Field(
        default=None,
        title="E-type",
        description="Optional electrical type tag.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    mtype: str | None = Field(
        default=None,
        title="M-type",
        description="Optional morphological type tag.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    ttype: str | None = Field(
        default=None,
        title="T-type",
        description="Optional transcriptomic type tag.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

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
        description="Pass ``use_multiprocessing=True`` to ``EModel_pipeline``.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    use_ipyparallel: bool = Field(
        default=False,
        title="Use ipyparallel",
        description="Pass ``use_ipyparallel=True`` to ``EModel_pipeline``.",
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

    optimiser: Literal["SO-CMA", "MO-CMA", "IBEA"] = Field(
        default="SO-CMA",
        title="Optimiser",
        description=(
            "BluePyEModel optimiser. ``SO-CMA`` is the single-objective"
            " Covariance Matrix Adaptation Evolution Strategy (commonly"
            " referred to as 'CMA-ES'); ``MO-CMA`` is its multi-objective"
            " variant (the L5PC recipe default); ``IBEA`` is the"
            " Indicator-Based Evolutionary Algorithm. See"
            " ``bluepyemodel.optimisation.optimisation.setup_optimiser``."
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
