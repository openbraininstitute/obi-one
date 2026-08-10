"""Blocks for the 02_emodel_optimization stage."""

from typing import Annotated, Any, ClassVar, Literal

from pydantic import (
    Discriminator,
    Field,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    model_validator,
)

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.etype_class_from_id import ETypeClassFromID
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID


class DistanceDependentDistribution(Block):
    """A BluePyEModel distance-dependent parameter transformation."""

    name: str | None = Field(
        default=None,
        min_length=1,
        title="Distribution name",
        description="Optional name used by BluePyEModel parameter definitions.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    function: str | None = Field(
        default=None,
        title="Distance function",
        description=(
            "Expression using {value} and {distance}; custom expressions may also use "
            "placeholders defined by the corresponding parameter configuration."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    soma_ref_location: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        title="Soma reference location",
        description="Reference location of the soma along the morphology.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    @model_validator(mode="after")
    def validate_function(self) -> "DistanceDependentDistribution":
        """Require custom functions to expose the value and distance inputs."""
        if self.function is not None and "{value}" not in self.function:
            msg = "Distance-dependent functions must contain the {value} placeholder."
            raise ValueError(msg)
        if self.function is not None and "{distance}" not in self.function:
            msg = "Distance-dependent functions must contain the {distance} placeholder."
            raise ValueError(msg)
        return self

    def to_emc_dict(self, name: str | None = None) -> dict[str, str | float | None]:
        """Convert the block to the legacy EMC distribution representation."""
        return {
            "name": name or self.name,
            "function": self.function,
            "soma_ref_location": self.soma_ref_location,
        }


class UniformDistanceDependentDistribution(DistanceDependentDistribution):
    """Default uniform distance distribution used by EMC files."""

    name: str = Field(default="uniform", frozen=True)
    function: None = Field(default=None, frozen=True)


class ExponentialDistanceDependentDistribution(DistanceDependentDistribution):
    """Standard exponential distance distribution used by SSCX and thalamus EMC files."""

    name: str = Field(default="exp", frozen=True)
    function: str = Field(
        default="(-0.8696 + 2.087*math.exp(({distance})*0.0031))*{value}",
        frozen=True,
    )


class StepDistanceDependentDistribution(DistanceDependentDistribution):
    """Step distance distribution used by detailed SSCX models."""

    name: str = Field(default="step", frozen=True)
    function: str = Field(
        default="{value} * (0.1 + 0.9 * int(({distance} > {step_begin}) & "
        "({distance} < {step_end})))",
        frozen=True,
    )


class ExponentialNaDendDistanceDependentDistribution(DistanceDependentDistribution):
    """Exponential dendritic sodium distance distribution used by hippocampus models."""

    name: str = Field(default="exp_na_dend", frozen=True)
    function: str = Field(default="math.exp((-{distance})/50)*{value}", frozen=True)


class LinearHDApicDistanceDependentDistribution(DistanceDependentDistribution):
    """Linear h-current apical distance distribution used by hippocampus models."""

    name: str = Field(default="linear_hd_apic", frozen=True)
    function: str = Field(default="(1. + 3./100. * {distance})*{value}", frozen=True)


class SigmoidKADApicDistanceDependentDistribution(DistanceDependentDistribution):
    """Sigmoid potassium A-current apical distance distribution."""

    name: str = Field(default="sigmoid_kad_apic", frozen=True)
    function: str = Field(
        default="(15./(1. + math.exp((300-{distance})/50)))*{value}",
        frozen=True,
    )


class LinearEPasApicDistanceDependentDistribution(DistanceDependentDistribution):
    """Linear passive reversal-potential apical distance distribution."""

    name: str = Field(default="linear_e_pas_apic", frozen=True)
    function: str = Field(default="({value}-5*{distance}/150)", frozen=True)


class CustomDistanceDependentDistribution(DistanceDependentDistribution):
    """User-defined distance-dependent distribution for the optimization workflow."""

    title: ClassVar[str] = "Custom Distance-Dependent Distribution"
    function: str = Field(
        min_length=1,
        title="Custom distance function",
        description="Python expression containing at least {value} and {distance}.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )


DistanceDependentDistributionUnion = Annotated[
    UniformDistanceDependentDistribution
    | ExponentialDistanceDependentDistribution
    | StepDistanceDependentDistribution
    | ExponentialNaDendDistanceDependentDistribution
    | LinearHDApicDistanceDependentDistribution
    | SigmoidKADApicDistanceDependentDistribution
    | LinearEPasApicDistanceDependentDistribution
    | CustomDistanceDependentDistribution,
    Discriminator("type"),
]


class OptimizationInitialize(Block):
    """Entity-based inputs for the optimisation stage."""

    target_efeatures: TaskResultFromID = Field(
        title="Target EFeatures",
        description=(
            "TaskResult entity from the 01_efeature_extraction stage. Assets"
            " (extracted features, recipes, targets config) are downloaded from"
            " this entity to seed the optimisation working directory."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER},
    )

    emodel: str = Field(
        title="E-Model name",
        description="Top-level key in ``recipes.json`` to operate on (e.g. ``L5PC``).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    morphology: CellMorphologyFromID = Field(
        title="Cell morphology",
        description=(
            "Morphology entity whose SWC/ASC asset is staged into"
            " ``./morphologies/``. The m-type, species and brain region are all"
            " derived from this entity."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER},
    )
    etype: ETypeClassFromID = Field(
        title="E-type",
        description="Electrical type entity selected from the database.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
            SchemaKey.ENTITY_QUERY: {
                "type": "etype",
            },
        },
    )


def _default_distance_dependent_distributions() -> dict[str, UniformDistanceDependentDistribution]:
    return {"uniform": UniformDistanceDependentDistribution()}


class ParametersSelection(Block):
    """Parameters selection — ion channel models for dynamic builder."""

    ion_channel_models: tuple[IonChannelModelFromID, ...] = Field(
        default_factory=tuple,
        title="Ion channel models",
        description=(
            "Ion channel model entities whose ``.mod`` assets are staged into"
            " ``./mechanisms/``. The params file is built dynamically from these"
            " models."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER_MULTIPLE},
    )

    distance_dependent_distributions: dict[str, DistanceDependentDistributionUnion] = Field(
        default_factory=_default_distance_dependent_distributions,
        title="Distance-dependent distributions",
        description=(
            "Distance-dependent parameter transformations used only by emodel optimization. "
            "Add a Custom Distance-Dependent Distribution to define a new expression."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.SINGULAR_NAME: "Distance-Dependent Distribution",
        },
    )


class OptimizationParams(Block):
    """``optimisation_params`` block (passed verbatim to BluePyEModel)."""

    offspring_size: PositiveInt | list[PositiveInt] = Field(
        default=20,
        le=200,
        title="Offspring size",
        description=(
            "Population size per generation. The L5PC example uses 20; we default"
            " to a small value so the bundled example completes quickly."
            " Allowed range: 1-200."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    def to_dict(self) -> dict:
        return {"offspring_size": self.offspring_size}


class OptimizationSettings(Block):
    """Top-level ``pipeline_settings`` keys controlling optimisation + analysis + export."""

    optimiser: Literal["SO-CMA", "MO-CMA", "IBEA"] = Field(
        default="MO-CMA",
        title="Optimiser",
        description=(
            "BluePyEModel optimiser. ``SO-CMA`` is the single-objective"
            " Covariance Matrix Adaptation Evolution Strategy (commonly"
            " referred to as 'CMA-ES'); ``MO-CMA`` is its multi-objective"
            " variant (the L5PC recipe default); ``IBEA`` is the"
            " Indicator-Based Evolutionary Algorithm."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    max_ngen: PositiveInt | list[PositiveInt] = Field(
        default=100,
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
            "plot_currentscape": True,
        }
