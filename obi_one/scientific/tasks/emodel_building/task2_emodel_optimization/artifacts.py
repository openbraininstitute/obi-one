"""Versioned, pure artifacts for the launch-system EModel optimization consumer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

from obi_one.scientific.tasks.emodel_building import _shared
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.parameter_builder import (
    MorphologyCapabilities,
    NormalizedIonChannelModel,
    build_params_definition,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.section_lists import (
    DEFAULT_SECTION_LIST_CATALOG,
)

TASK2_CONFIG_CONTRACT_VERSION = "task2-config-v1"
TASK2_ARTIFACT_CONTRACT_VERSION = "task2-artifacts-v1"
PARAMS_ARTIFACT_PATH = "config/params/params.json"
RECIPES_ARTIFACT_PATH = "config/recipes.json"


@dataclass(frozen=True, slots=True)
class OptimizationArtifacts:
    """JSON-ready Task 2 artifacts and their portable coordinate-root paths."""

    config_contract_version: str
    artifact_contract_version: str
    params: dict[str, Any]
    recipes: dict[str, dict[str, Any]]
    params_path: str = PARAMS_ARTIFACT_PATH
    recipes_path: str = RECIPES_ARTIFACT_PATH

    def write(self, coordinate_root: Path) -> None:
        """Write the bundle below a coordinate root using only contract paths."""
        _write_json(coordinate_root / self.params_path, self.params)
        _write_json(coordinate_root / self.recipes_path, self.recipes)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=4), encoding="utf-8")


def _validate_relative_filename(filename: str, field_name: str) -> None:
    path = Path(filename)
    if path.is_absolute() or path.name != filename or ".." in path.parts:
        msg = f"{field_name} must be a relative filename, got {filename!r}."
        raise ValueError(msg)


def build_optimization_recipe(
    emodel: str,
    mtype: str | None,
    morph_filename: str,
    params_filename: str = "params.json",
) -> dict[str, dict[str, Any]]:
    """Build the deterministic BluePyEModel recipe for one optimization coordinate."""
    _validate_relative_filename(morph_filename, "morph_filename")
    _validate_relative_filename(params_filename, "params_filename")
    if params_filename != Path(PARAMS_ARTIFACT_PATH).name:
        msg = f"params_filename must be {Path(PARAMS_ARTIFACT_PATH).name!r}."
        raise ValueError(msg)
    return {
        emodel: {
            "morph_path": "./morphologies/",
            "morphology": [[mtype, morph_filename]],
            "features": f"config/features/{emodel}.json",
            "params": f"config/params/{params_filename}",
            "multiloc_map": DEFAULT_SECTION_LIST_CATALOG.to_recipe_multiloc_map(),
        }
    }


def build_optimization_artifacts(
    config: Any,
    normalized_ion_channel_models: Mapping[str, NormalizedIonChannelModel],
    *,
    mtype: str | None,
    morphology_filename: str,
    morphology_capabilities: MorphologyCapabilities | None = None,
) -> OptimizationArtifacts:
    """Compile the validated Task 2 config into the launch-system artifact bundle.

    This function is deliberately pure: entity resolution, downloads, filesystem staging,
    mechanism compilation, optimization, and registration remain outside the boundary.
    """
    config_contract_version = getattr(config, "contract_version", None)
    if config_contract_version != TASK2_CONFIG_CONTRACT_VERSION:
        msg = (
            "Unsupported Task 2 configuration contract version: "
            f"{config_contract_version!r}; expected {TASK2_CONFIG_CONTRACT_VERSION!r}."
        )
        raise ValueError(msg)

    emodel = config.initialize.emodel
    params = build_params_definition(
        config,
        normalized_ion_channel_models,
        morphology_capabilities=morphology_capabilities,
    )
    recipes = build_optimization_recipe(emodel, mtype, morphology_filename)
    _shared.update_pipeline_settings(
        recipes,
        emodel=emodel,
        overrides={
            **config.morphology_settings.to_pipeline_settings(),
            **config.optimization_settings.to_dict(config.optimization_params),
        },
    )
    return OptimizationArtifacts(
        config_contract_version=config_contract_version,
        artifact_contract_version=TASK2_ARTIFACT_CONTRACT_VERSION,
        params=params,
        recipes=recipes,
    )
