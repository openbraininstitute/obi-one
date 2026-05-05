"""Blocks for the 02_analysis_and_validation stage."""

from pathlib import Path
from typing import Any

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement


class AnalysisInitialize(Block):
    """Filesystem inputs for the analysis stage."""

    previous_stage_output_path: Path = Field(
        title="Previous stage output path",
        description=(
            "Path to the working directory produced by the 01_emodel_optimization stage"
            " (typically ``obi-output/01_emodel_optimization/grid_scan/0/``). The stage"
            " copies the recipes/config/morphologies/mechanisms/checkpoints from there."
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


class AnalysisSettings(Block):
    """Top-level ``pipeline_settings`` keys controlling analysis & validation."""

    validation_protocols: tuple[str, ...] = Field(
        default=("sAHP_220",),
        title="Validation protocols",
        description=(
            "Protocols held out from optimisation, used to validate the optimised"
            " models in the analysis step."
        ),
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
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
        default=False,
        title="Only validated plots",
        description="Forward as ``only_validated`` to ``pipeline.plot()``.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
    )

    def to_dict(self, currentscape: CurrentscapeConfig) -> dict[str, Any]:
        return {
            "validation_protocols": list(self.validation_protocols),
            "plot_currentscape": self.plot_currentscape,
            "save_recordings": self.save_recordings,
            "currentscape_config": currentscape.to_dict(),
        }
