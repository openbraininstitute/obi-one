"""Blocks for the 03_export_final_model stage."""

from pathlib import Path

from pydantic import Field, NonNegativeInt

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement


class ExportInitialize(Block):
    """Filesystem inputs for the export stage."""

    previous_stage_output_path: Path = Field(
        title="Previous stage output path",
        description=(
            "Path to the working directory produced by the 02_analysis_and_validation"
            " stage (typically ``obi-output/02_analysis_and_validation/grid_scan/0/``)."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )

    emodel: str = Field(
        title="E-Model name",
        description="Top-level key in ``recipes.json`` (must match the previous stage).",
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


class ExportSettings(Block):
    """Flags for ``export_emodels_hoc`` / ``export_emodels_sonata``."""

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
        default=False,
        title="Only validated",
        description="Forward as ``only_validated`` to the export functions.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )
    only_best: bool = Field(
        default=False,
        title="Only best",
        description="Forward as ``only_best`` to the export functions.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    seeds: tuple[NonNegativeInt, ...] = Field(
        default=(1,),
        title="Seeds",
        description=("Seeds to export. Must be a subset of the seeds optimised in stage 01."),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
