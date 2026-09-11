"""Entity registration for Task 2 optimisation outputs.

Registers the TaskResult, draft EModel, and draft MEModel after BluePyEModel
has written checkpoints, figures, and ``final.json`` into the working directory.
"""

import inspect
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import entitysdk

from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (
    EModelOptimizationSingleConfig,
)

L = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegisteredOptimizationOutputs:
    """IDs of entities registered after a local optimisation run."""

    task_result_id: str
    emodel_id: str
    memodel_id: str


def validation_status_keyword(register_emodel: Any) -> str:
    """Select the validation-status keyword supported by an EntitySDK helper."""
    try:
        parameters = inspect.signature(register_emodel).parameters
    except (TypeError, ValueError):
        return "validation_result_status"
    if "validation_result_status" in parameters:
        return "validation_result_status"
    if "validateion_result_status" in parameters:
        return "validateion_result_status"
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return "validation_result_status"
    msg = (
        "EntitySDK register_emodel does not expose validation_result_status or "
        "validateion_result_status."
    )
    raise TypeError(msg)


def parse_final_json(final_path: Path, emodel_name: str) -> dict:
    """Parse final.json (written by store_best_model) for score, calibration, iteration.

    BluePyEModel's ``store_best_model`` writes ``final.json`` at the
    coordinate output root. Its structure is::

        {emodel_name: [{fitness, holding_current, threshold_current, ...}]}

    Returns a dict with keys: name, total_score, holding_current,
    threshold_current, iteration.
    """
    defaults = {
        "name": emodel_name,
        "total_score": 0.0,
        "holding_current": None,
        "threshold_current": None,
        "iteration": "0",
    }
    if not final_path.exists():
        L.warning("final.json not found at %s; using defaults for registration.", final_path)
        return defaults

    data = json.loads(final_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return defaults

    models = data.get(emodel_name, [])
    if not models:
        # Try the placeholder key "emodel" that extraction stage writes
        models = data.get("emodel", [])
    if not models:
        return defaults

    best = models[0] if isinstance(models, list) else models
    total_score = float(best.get("fitness", best.get("score", 0.0)))
    holding_current = best.get("holding_current")
    threshold_current = best.get("threshold_current")

    # Iteration from the model dict or filename convention
    iteration = str(best.get("iteration", "0"))

    return {
        "name": emodel_name,
        "total_score": total_score,
        "holding_current": holding_current,
        "threshold_current": threshold_current,
        "iteration": iteration,
    }


def upload_optimization_assets(
    coord_root: Path,
    db_client: entitysdk.Client,
    task_result_id: str,
) -> None:
    """Upload recipes, params, and the SONATA export to the TaskResult."""
    from entitysdk.models import TaskResult  # ruff: ignore[import-outside-top-level]
    from entitysdk.types import (  # ruff: ignore[import-outside-top-level]
        AssetLabel,
        ContentType,
    )

    # Recipes.json — needed by task3 to reconstruct pipeline settings
    recipes_path = coord_root / "config" / "recipes.json"
    if recipes_path.exists():
        db_client.upload_file(
            entity_id=task_result_id,  # ty:ignore[invalid-argument-type]
            entity_type=TaskResult,
            file_path=recipes_path,
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.task_result,
        )
        L.info("Uploaded recipes.json to TaskResult.")

    # Params file — needed by task3 for mechanism parameters
    params_path = coord_root / "config" / "params" / "params.json"
    if params_path.exists():
        db_client.upload_file(
            entity_id=task_result_id,  # ty:ignore[invalid-argument-type]
            entity_type=TaskResult,
            file_path=params_path,
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.neuron_mechanisms,
        )
        L.info("Uploaded params.json to TaskResult.")

    # SONATA directory — needed by task3 for final export
    sonata_dir = coord_root / "export_emodels_sonata"
    if sonata_dir.exists() and any(sonata_dir.rglob("*")):
        db_client.upload_directory(
            entity_id=task_result_id,  # ty:ignore[invalid-argument-type]
            entity_type=TaskResult,
            paths={p.relative_to(sonata_dir): p for p in sonata_dir.rglob("*") if p.is_file()},
            name=AssetLabel.emodel_optimization_output,
            label=AssetLabel.emodel_optimization_output,
        )
        L.info("Uploaded SONATA to TaskResult.")


def register_output_entities(  # ruff: ignore[too-many-locals]
    config: EModelOptimizationSingleConfig,
    coord_root: Path,
    db_client: entitysdk.Client,
    *,
    trace_ids: list | None = None,
    execution_activity_id: str | None = None,
) -> RegisteredOptimizationOutputs:
    """Register TaskResult, draft EModel, draft MEModel using entitysdk helpers.

    Uses the shared ``entitysdk.registration`` helper package so this local path and
    the remote launch-system worker register output entities identically. Raises
    ``RuntimeError`` if the installed EntitySDK release does not provide that package.
    """
    from entitysdk.models import (  # ruff: ignore[import-outside-top-level]
        License,
        TaskActivity,
    )

    try:
        from entitysdk.registration.emodel import (  # ruff: ignore[import-outside-top-level]  # ty:ignore[unresolved-import]
            register_emodel,
        )
        from entitysdk.registration.memodel import (  # ruff: ignore[import-outside-top-level]  # ty:ignore[unresolved-import]
            register_memodel,
        )
        from entitysdk.registration.task_result.emodel_optimization import (  # ruff: ignore[import-outside-top-level]  # ty:ignore[unresolved-import]
            register_emodel_optimization_result,
        )
    except ModuleNotFoundError as exc:
        msg = (
            "Task 2 output registration requires an EntitySDK release that provides "
            "entitysdk.registration.emodel, entitysdk.registration.memodel, and "
            "entitysdk.registration.task_result.emodel_optimization."
        )
        raise RuntimeError(msg) from exc
    from entitysdk.types import (  # ruff: ignore[import-outside-top-level]
        EntityLifecycleStatus,
        ValidationStatus,
    )

    init = config.initialize
    emodel_name = init.emodel
    seed = int(config.optimization_settings.seed)  # ty:ignore[invalid-argument-type]

    # --- Gather metadata ---
    # Species and brain region come from the morphology entity, so the
    # registered emodel/me-model inherit the morphology's provenance.
    morph_entity = config.inputs.morphology.entity(db_client=db_client)
    species_entity, brain_region_entity = config.inputs.morphology.metadata_entities(
        db_client=db_client
    )

    # Fetch license (CC-BY-4.0)
    license_entity = db_client.search_entity(
        entity_type=License,
        query={"name": "CC-BY-4.0"},
    ).one()

    # ETypeClass entity from user selection
    etype_class = init.etype.entity(db_client=db_client)

    # Determine authorized_public from execution activity if available
    authorized_public = False
    if execution_activity_id is not None:
        activity = db_client.get_entity(
            entity_id=execution_activity_id,  # ty:ignore[invalid-argument-type]
            entity_type=TaskActivity,
        )
        authorized_public = getattr(activity, "authorized_public", False)

    # --- Parse emodel JSON for metrics ---
    final_path = coord_root / "final.json"
    em_metrics = parse_final_json(final_path, emodel_name)

    # --- Collect file paths for helpers ---
    # Checkpoints: BluePyEModel writes .pkl files by default (not HDF5).
    # The entitysdk helper parameter is named hdf5_checkpoint_file but accepts
    # any checkpoint format.
    checkpoint_dir = coord_root / "checkpoints"
    checkpoint_file = None
    if checkpoint_dir.exists():
        for ckpt in checkpoint_dir.rglob("*.pkl"):
            checkpoint_file = ckpt
            break

    # Figures directory (ensure it exists for the helper)
    figures_dir = coord_root / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Summary file: use final.json (written by store_best_model)
    final_path = coord_root / "final.json"
    emodel_summary_file = final_path if final_path.exists() else None

    # Collect validation result figure files
    validation_figures: list[Path] = []
    if figures_dir.exists():
        validation_figures = [
            fp
            for fp in sorted(figures_dir.rglob("*"))
            if fp.is_file() and fp.suffix in {".pdf", ".png"}
        ]

    # --- Register TaskResult via helper ---
    task_result = register_emodel_optimization_result(
        client=db_client,
        name=f"EModel Optimization Result — {emodel_name}",
        description=f"Optimisation + analysis + export for emodel '{emodel_name}'.",
        authorized_public=authorized_public,
        hdf5_checkpoint_file=checkpoint_file,
        analysis_figures_dir=figures_dir,
        summary_file=emodel_summary_file,
    )
    L.info("TaskResult registered: %s", task_result.id)

    # --- Upload additional assets needed by task3 (export + validation) ---
    upload_optimization_assets(coord_root, db_client, task_result.id)

    # --- Collect ion channel model entities ---
    references = config.parameters_selection.ion_channel_model_references
    ion_channel_models = [reference.entity(db_client=db_client) for reference in references]

    # --- Register draft EModel via helper ---
    hoc_file = None
    status_keyword = validation_status_keyword(register_emodel)
    emodel_entity = register_emodel(
        client=db_client,
        name=f"{emodel_name} (draft)",
        description=f"Draft emodel from optimisation (emodel={emodel_name}).",
        authorized_public=authorized_public,
        species=species_entity,
        brain_region=brain_region_entity,
        license=license_entity,
        seed=seed,
        iteration=em_metrics["iteration"],
        score=em_metrics["total_score"],
        exemplar_morphology=morph_entity,
        ion_channel_models=ion_channel_models,
        lifecycle_status=EntityLifecycleStatus.draft,
        etype_class=etype_class,
        hoc_file=hoc_file,
        emodel_summary_file=emodel_summary_file,
        electrical_cell_recording_ids=trace_ids or [],
        validation_result_figure_files=validation_figures,
        **{status_keyword: False},
    )
    L.info("Draft EModel registered: %s", emodel_entity.id)

    # --- Register draft MEModel via helper ---
    memodel_entity = register_memodel(
        client=db_client,
        name=f"{emodel_name} MEModel (draft)",
        description=f"Draft MEModel from optimisation (emodel={emodel_name}).",
        species=species_entity,
        brain_region=brain_region_entity,
        license=license_entity,
        morphology=morph_entity,
        emodel=emodel_entity,
        threshold_current=em_metrics["threshold_current"],
        holding_current=em_metrics["holding_current"],
        authorized_public=authorized_public,
        validation_status=ValidationStatus.created,
        lifecycle_status=EntityLifecycleStatus.draft,
    )
    L.info("Draft MEModel registered: %s", memodel_entity.id)

    # --- Update TaskActivity with generated_ids ---
    if execution_activity_id is not None:
        db_client.update_entity(
            entity_id=execution_activity_id,  # ty:ignore[invalid-argument-type]
            entity_type=TaskActivity,
            attrs_or_entity={
                "generated_ids": [task_result.id, emodel_entity.id, memodel_entity.id],
            },
        )

    return RegisteredOptimizationOutputs(
        task_result_id=str(task_result.id),
        emodel_id=str(emodel_entity.id),
        memodel_id=str(memodel_entity.id),
    )
