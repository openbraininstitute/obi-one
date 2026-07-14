"""Blocks for the 02_emodel_optimization stage."""

from typing import Any, Literal

from pydantic import Field, NonNegativeInt, PositiveFloat, PositiveInt

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
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
    etype: str = Field(
        title="E-type",
        description="Electrical type tag (selected by the user in the UI).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
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

    ion_channel_models: list[IonChannelModelFromID] = Field(
        default_factory=list,
        title="Ion channel models",
        description=(
            "Ion channel model entities whose ``.mod`` assets are staged into"
            " ``./mechanisms/``. The params file is built dynamically from these"
            " models."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER_MULTIPLE},
    )


class ParamsFileSelection(Block):
    """Params-file mode — provide a pre-built BluePyEModel params JSON file.

    The file must contain top-level keys ``mechanisms``, ``distributions``,
    and ``parameters``. Each parameter must have a ``name`` and ``val``;
    each ``dist`` reference must point to an existing distribution.
    """

    params_file_path: str = Field(
        default="",
        title="Params file path",
        description=(
            "Path to a BluePyEModel params JSON file. Must contain top-level"
            " keys: ``mechanisms``, ``distributions``, ``parameters``."
            " Leave empty to use the dynamic builder."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    mechanisms_dir_path: str = Field(
        default="",
        title="Mechanisms directory path",
        description=(
            "Optional path to a directory of ``.mod`` files. If not provided,"
            " mechanisms are expected to already be available in the working"
            " directory."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )


def validate_params_file(params: dict) -> None:
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
    if not isinstance(parameters, list):
        msg = f"'parameters' must be a list, got {type(parameters).__name__}."
        raise OBIONEError(msg)

    for i, param in enumerate(parameters):
        if not isinstance(param, dict):
            msg = f"Parameter at index {i} must be a dict, got {type(param).__name__}."
            raise OBIONEError(msg)
        if "name" not in param:
            msg = f"Parameter at index {i} is missing required key 'name'."
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
    """Top-level ``pipeline_settings`` keys controlling optimisation + analysis + export."""

    optimiser: Literal["SO-CMA", "MO-CMA", "IBEA"] = Field(
        default="SO-CMA",
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

    # Analysis settings (used by pipeline.plot() after optimisation)
    plot_currentscape: bool = Field(
        default=True,
        title="Plot currentscape",
        description="Generate currentscape plots during analysis.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    currentscape_title: str = Field(
        default="",
        title="Currentscape title",
        description="Title for currentscape plots.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    # Validation-related settings — preserved in recipe for Workflow B
    validation_protocols: str = Field(
        default="",
        title="Validation protocols",
        description=(
            "Comma-separated protocol names whose features are validation-only"
            " (marked ``validation: true`` in the features file). These are NOT"
            " optimisation targets but must be in the recipe for"
            " BluePyEModel data structure initialization."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    name_rin_protocol: str = Field(
        default="",
        title="Rin protocol name",
        description=(
            "Protocol name for input resistance measurement (e.g. ``IV_-20``)."
            " Required for threshold-based optimisations."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    name_rmp_protocol: str = Field(
        default="",
        title="RMP protocol name",
        description=(
            "Protocol name for resting membrane potential (e.g. ``IV_0``)."
            " Required for threshold-based optimisations."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    # Export settings
    export_hoc: bool = Field(
        default=True,
        title="Export HOC",
        description="Export the optimised emodel to NEURON HOC format.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    export_sonata: bool = Field(
        default=True,
        title="Export SONATA",
        description="Export the optimised emodel to SONATA format.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    only_best: bool = Field(
        default=False,
        title="Only best",
        description="If True, export only the best individual from optimisation.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    seeds: NonNegativeInt | list[NonNegativeInt] = Field(
        default=1,
        title="Export seeds",
        description="Seeds to use for export.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    def to_dict(self, optimisation_params: OptimizationParams) -> dict[str, Any]:
        result: dict[str, Any] = {
            "optimiser": self.optimiser,
            "max_ngen": self.max_ngen,
            "optimisation_timeout": self.optimisation_timeout,
            "validation_threshold": self.validation_threshold,
            "optimisation_params": optimisation_params.to_dict(),
            "plot_currentscape": self.plot_currentscape,
            "validation_protocols": [
                p.strip() for p in self.validation_protocols.split(",") if p.strip()
            ],
            "name_Rin_protocol": self.name_rin_protocol or None,
            "name_rmp_protocol": self.name_rmp_protocol or None,
        }

        if self.currentscape_title:
            result["currentscape_config"] = {"title": self.currentscape_title}

        return result
