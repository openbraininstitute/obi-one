"""Blocks for the 02_emodel_optimization stage."""

from typing import Any, Literal

from pydantic import Field, NonNegativeInt, PositiveFloat, PositiveInt

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.from_id.brain_region_from_id import BrainRegionFromID
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.etype_class_from_id import ETypeClassFromID
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.scientific.from_id.species_from_id import SpeciesFromID
from obi_one.scientific.from_id.task_config_from_id import TaskConfigFromID
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID


class OptimizationInitialize(Block):
    """Entity-based inputs for the optimisation stage."""

    extraction_task_result: TaskResultFromID = Field(
        title="Extraction TaskResult",
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
    species: SpeciesFromID = Field(
        title="Species",
        description="Species entity selected from the database.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
            SchemaKey.ENTITY_QUERY: {
                "type": "species",
            },
        },
    )
    brain_region: BrainRegionFromID = Field(
        title="Brain region",
        description="Brain region entity selected from the database.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
            SchemaKey.ENTITY_QUERY: {
                "type": "brain-region",
            },
        },
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


class MorphologySelection(Block):
    """Morphology entity selection for the optimisation stage."""

    morphology: CellMorphologyFromID = Field(
        title="Cell morphology",
        description=(
            "Morphology entity whose SWC/ASC asset will be staged into"
            " ``./morphologies/``. The m-type is derived from this entity."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER},
    )


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


class ParamsFileSelection(Block):
    """Params-file mode — select a pre-built BluePyEModel params JSON from a TaskConfig entity.

    The TaskConfig must have ``task_config_type=emodel_optimization__config``
    and contain a ``params.json`` asset with the standard BluePyEModel
    params structure (top-level keys: ``mechanisms``, ``distributions``,
    ``parameters``).
    """

    params_template: TaskConfigFromID | None = Field(
        default=None,
        title="Params template",
        description=(
            "Select a pre-built BluePyEModel params template from the database."
            " If set, this takes precedence over the dynamic builder."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
            SchemaKey.ENTITY_QUERY: {
                "type": "task_config",
                "task_config_type": "emodel_optimization__config",
            },
        },
    )


def validate_params_file(params: dict) -> None:  # noqa: C901, PLR0912
    """Validate the structure of a BluePyEModel params dictionary.

    Raises :class:`OBIONEError` if the structure is invalid.
    """
    from obi_one.core.exception import OBIONEError  # noqa: PLC0415

    required_keys = {"mechanisms", "distributions", "parameters"}
    missing = required_keys - set(params)
    if missing:
        msg = (
            f"Params file is missing required top-level keys: {sorted(missing)}."
            f" Expected keys: {sorted(required_keys)}."
        )
        raise OBIONEError(msg)

    distributions = params.get("distributions", {})
    if not isinstance(distributions, dict):
        msg = f"'distributions' must be a dict, got {type(distributions).__name__}."
        raise OBIONEError(msg)

    dist_names = set(distributions.keys())

    parameters = params.get("parameters", [])
    if isinstance(parameters, dict):
        param_sections = parameters.items()
    elif isinstance(parameters, list):
        param_sections = [("__root__", parameters)]
    else:
        msg = f"'parameters' must be a list or dict, got {type(parameters).__name__}."
        raise OBIONEError(msg)

    for section, section_params in param_sections:
        if section.startswith("__"):
            continue
        if not isinstance(section_params, list):
            msg = (
                f"Parameter section '{section}' must be a list,"
                f" got {type(section_params).__name__}."
            )
            raise OBIONEError(msg)
        for i, param in enumerate(section_params):
            if not isinstance(param, dict):
                msg = f"Parameter '{section}[{i}]' must be a dict, got {type(param).__name__}."
                raise OBIONEError(msg)
            if "name" not in param:
                msg = f"Parameter '{section}[{i}]' is missing required key 'name'."
                raise OBIONEError(msg)
            if "val" not in param:
                msg = f"Parameter '{param.get('name', i)}' is missing required key 'val'."  # ty:ignore[no-matching-overload]
                raise OBIONEError(msg)
            dist = param.get("dist")  # ty:ignore[invalid-argument-type]
            if dist is not None and dist not in dist_names:
                msg = (
                    f"Parameter '{param['name']}' references distribution '{dist}'"  # ty:ignore[invalid-argument-type]
                    f" which is not defined in 'distributions'"
                    f" (available: {sorted(dist_names)})."
                )
                raise OBIONEError(msg)


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
