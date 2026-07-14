"""Blocks for the 03_export_and_validation stage (Workflow B).

Combines validation + export in a single task. Consumes the optimisation
TaskResult from Workflow A, runs validation, plots, and final export.
"""

from typing import Any

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID


class ExportAndValidationInitialize(Block):
    """Entity-based inputs for the export + validation stage."""

    optimization_task_result: TaskResultFromID = Field(
        title="Optimization TaskResult",
        description=(
            "TaskResult entity from the 02_emodel_optimization stage (Workflow A)."
            " Assets (checkpoint, final.json, recipes, params, figures, hoc, sonata)"
            " are downloaded from this entity to seed the working directory."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER},
    )

    memodel: MEModelFromID = Field(
        title="MEModel to update",
        description=(
            "Draft MEModel entity registered by the optimisation stage."
            " Validation results (holding_current, threshold_current, Rin,"
            " validation_status) will be updated on this entity."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER},
    )

    emodel: str = Field(
        title="E-Model name",
        description="Top-level key in ``recipes.json`` (must match optimisation stage).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    species: str = Field(
        default="rat",
        title="Species",
        description="Species for the model (e.g. ``rat``, ``mouse``).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    brain_region: str = Field(
        default="SSCX",
        title="Brain region",
        description="Brain region for the model (e.g. ``SSCX``).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    etype: str = Field(
        title="E-type",
        description="Electrical type tag (must match optimisation stage).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    iteration_tag: str | None = Field(
        default=None,
        title="Iteration tag",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    use_multiprocessing: bool = Field(
        default=False,
        title="Use multiprocessing",
        description="If True, use multiprocessing for parallel execution.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    use_ipyparallel: bool = Field(
        default=False,
        title="Use ipyparallel",
        description="If True, use ipyparallel for parallel execution.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )


class CurrentscapeConfig(Block):
    """Subset of the BluePyEModel ``currentscape_config``."""

    figure_title: str = Field(
        default="EModel",
        title="Currentscape title",
        description="Title rendered on currentscape figures.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    def to_dict(self) -> dict:
        return {"title": self.figure_title}


class ExportAndValidationSettings(Block):
    """Settings controlling validation, plotting, and export."""

    # Validation settings
    validation_protocols: str = Field(
        default="sAHP_220",
        title="Validation protocols",
        description=(
            "Comma-separated protocol names held out from optimisation,"
            " used to validate the optimised models."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    validation_threshold: float | list[float] = Field(
        default=5.0,
        title="Validation threshold",
        description="Z-score threshold below which a model is considered validated.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    # Plotting settings
    plot_currentscape: bool = Field(
        default=True,
        title="Plot currentscape",
        description="Whether to render currentscape (per-current contribution) plots.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    save_recordings: bool = Field(
        default=False,
        title="Save recordings",
        description="Whether to dump voltage/current traces under ``./recordings/``.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    only_validated_plots: bool = Field(
        default=True,
        title="Only validated plots",
        description="Forward as ``only_validated`` to ``pipeline.plot()``.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    # Export settings
    export_hoc: bool = Field(
        default=True,
        title="Export HOC",
        description="Whether to call ``export_emodels_hoc``.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    export_sonata: bool = Field(
        default=True,
        title="Export SONATA",
        description="Whether to call ``export_emodels_sonata``.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    only_validated: bool = Field(
        default=True,
        title="Only validated",
        description="Forward as ``only_validated`` to the export functions.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    only_best: bool = Field(
        default=True,
        title="Only best",
        description="Forward as ``only_best`` to the export functions.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    seeds: str = Field(
        default="1",
        title="Seeds",
        description="Comma-separated seeds to export. Must be a subset of the seeds optimised.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    def to_dict(self, currentscape: CurrentscapeConfig) -> dict[str, Any]:
        return {
            "validation_protocols": [
                p.strip() for p in self.validation_protocols.split(",") if p.strip()
            ],
            "validation_threshold": self.validation_threshold,
            "plot_currentscape": self.plot_currentscape,
            "save_recordings": self.save_recordings,
            "currentscape_config": currentscape.to_dict(),
        }
