"""Entity registration for Task 2 optimisation outputs.

Registers the TaskResult, draft EModel, and draft MEModel after BluePyEModel
has written checkpoints, figures, and ``final.json`` into the working directory.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID

import entitysdk
from entitysdk import MultipartDirectoryUploadTransferConfig
from entitysdk.models import (
    CellMorphology,
    ETypeClass,
    IonChannelModel,
    License,
    MEModelCalibrationResult,
    TaskActivity,
    TaskResult,
    ValidationResult,
)
from entitysdk.registration.emodel import register_emodel
from entitysdk.registration.memodel import register_memodel
from entitysdk.registration.validation_result import SUFFIX_TO_NAME
from entitysdk.types import (
    ID,
    AssetLabel,
    ContentType,
    EntityLifecycleStatus,
    TaskResultType,
    ValidationStatus,
)

from obi_one.db_sdk import db_sdk
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
    authorized_public: bool
    generated_ids: list[str]


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
    task_result_id: ID,
) -> None:
    """Upload recipes, params, and the SONATA export to the TaskResult.

    Currently a no-op: entitycore's ``ALLOWED_ASSET_LABELS_PER_TASK_RESULT`` for
    ``TaskResultType.emodel_optimization__result`` only allows
    ``emodel_optimisation_checkpoint``, ``emodel_analysis_figures``, and
    ``emodel_analysis_summary`` (see entitycore ``app/db/types.py``). The labels this
    function used to pass — ``AssetLabel.task_result``, ``AssetLabel.neuron_mechanisms``,
    and ``AssetLabel.emodel_optimization_output`` — are not in that allow-list (the last
    one is reserved for the ``EModel`` entity, where ``register_emodel`` already uploads
    ``final.json`` under it) and every upload here raised a 422 ``ASSET_INVALID_SCHEMA``
    error. Re-enable once entitycore adds asset labels for recipes/params/SONATA on
    ``TaskResult``.
    """
    recipes_path = coord_root / "config" / "recipes.json"
    params_path = coord_root / "config" / "params" / "params.json"
    sonata_dir = coord_root / "export_emodels_sonata"
    if (
        recipes_path.exists()
        or params_path.exists()
        or (sonata_dir.exists() and any(sonata_dir.rglob("*")))
    ):
        L.warning(
            "Skipping upload of recipes.json/params.json/SONATA export to TaskResult(id=%s): "
            "entitycore has no allowed asset label for these on task_result_type "
            "'emodel_optimization__result'.",
            task_result_id,
        )


def register_output_entities(  # ruff: ignore[too-many-locals,too-many-statements,complex-structure]
    config: EModelOptimizationSingleConfig,
    coord_root: Path,
    db_client: entitysdk.Client,
    *,
    trace_ids: list | None = None,
    execution_activity_id: str | None = None,
    em_metrics: dict | None = None,
    calibration: dict | None = None,
    validation: dict | None = None,
    validation_status: ValidationStatus = ValidationStatus.created,
) -> RegisteredOptimizationOutputs:
    """Register TaskResult, EModel, MEModel (+ calibration/validation) in one pass.

    Uses the shared ``entitysdk.registration`` helper package so this local path and
    the remote launch-system worker register output entities identically.

    ``em_metrics``/``calibration``/``validation``/``validation_status`` come from
    :func:`task.run_optimization_pipeline` (which parses ``final.json`` and runs
    the subprocesses). When ``calibration``/``validation`` are provided, a
    ``MEModelCalibrationResult`` and per-test ``ValidationResult`` entities are
    registered against the MEModel, which itself is registered with the final
    ``validation_status``.
    """
    init = config.initialize
    emodel_name = init.emodel
    seed = int(config.optimization_settings.seed)  # ty:ignore[invalid-argument-type]

    # --- Gather metadata ---
    # Species and brain region come from the morphology entity, so the
    # registered emodel/me-model inherit the morphology's provenance.
    morph_entity = cast("CellMorphology", config.initialize.morphology.entity(db_client=db_client))
    species_entity, brain_region_entity = config.initialize.morphology.metadata_entities(
        db_client=db_client
    )

    # Fetch license (CC-BY-4.0)
    license_entity = db_client.search_entity(
        entity_type=License,
        query={"label": "CC BY 4.0"},
    ).one()

    # ETypeClass entity from user selection
    etype_class = cast("ETypeClass", init.etype.entity(db_client=db_client))

    # Determine authorized_public from execution activity if available
    authorized_public = False
    if execution_activity_id is not None:
        activity = db_client.get_entity(
            entity_id=execution_activity_id,  # ty:ignore[invalid-argument-type]
            entity_type=TaskActivity,
        )
        authorized_public = getattr(activity, "authorized_public", False)

    # --- Parse emodel JSON for metrics (reuse the pipeline's parse when given) ---
    final_path = coord_root / "final.json"
    if em_metrics is None:
        em_metrics = parse_final_json(final_path, emodel_name)

    # --- Collect file paths for helpers ---
    # Checkpoints: BluePyOpt writes .pkl files; task.py converts them to .h5
    # via bluepyemodel.tools.checkpoint_hdf5.convert_checkpoint before registration.
    # A missing checkpoint/summary/figures set means optimisation, storage, or
    # plotting did not actually succeed (BluePyEModel can fail some of these steps
    # without raising — see plot_models/export_emodels_sonata), so we fail loudly
    # here rather than silently registering an incomplete TaskResult.
    checkpoint_dir = coord_root / "checkpoints"
    checkpoint_file = next(checkpoint_dir.rglob("*.h5"), None) if checkpoint_dir.exists() else None
    if checkpoint_file is None:
        msg = (
            f"No .h5 checkpoint found under {checkpoint_dir}. Optimisation did not "
            "produce a valid checkpoint; refusing to register an incomplete TaskResult."
        )
        raise RuntimeError(msg)

    figures_dir = coord_root / "figures"
    figure_files: dict[Path, Path] = {}
    if figures_dir.exists():
        figure_files = {
            p.relative_to(figures_dir): p for p in sorted(figures_dir.rglob("*")) if p.is_file()
        }
    if not figure_files:
        msg = (
            f"No analysis figures found under {figures_dir}. Plotting did not produce "
            "any output; refusing to register an incomplete TaskResult."
        )
        raise RuntimeError(msg)

    # Summary file: use final.json (written by store_best_model)
    emodel_summary_file = final_path
    if not emodel_summary_file.exists():
        msg = (
            f"final.json not found at {emodel_summary_file}. store_best_model did not "
            "produce a summary; refusing to register an incomplete TaskResult."
        )
        raise RuntimeError(msg)

    # Collect validation result figure files
    validation_figures: list[Path] = [
        fp
        for fp in sorted(figures_dir.rglob("*"))
        if fp.is_file() and fp.suffix in {".pdf", ".png"}
    ]

    # --- Register TaskResult ---
    # entitysdk's register_emodel_optimization_result uses iterdir() on
    # analysis_figures_dir, which only finds top-level files. BluePyEModel writes
    # figures into nested subdirectories (e.g. figures/L5PC/scores/all/), so we
    # inline the registration here and collect figure files recursively with rglob.
    task_result = db_client.register_entity(
        TaskResult(
            name=f"EModel Optimization Result — {emodel_name}",
            description=f"Optimisation + analysis + export for emodel '{emodel_name}'.",
            authorized_public=authorized_public,
            task_result_type=TaskResultType.emodel_optimization__result,
        )
    )
    db_client.upload_file(
        entity_id=task_result.id,
        entity_type=TaskResult,
        file_path=checkpoint_file,
        file_content_type=ContentType.application_x_hdf5,
        asset_label=AssetLabel.emodel_optimisation_checkpoint,
    )
    db_client.upload_directory(
        entity_id=task_result.id,
        entity_type=TaskResult,
        paths=dict(figure_files),
        name="analysis_figures",
        label=AssetLabel.emodel_analysis_figures,
        transfer_config=MultipartDirectoryUploadTransferConfig(),
    )
    db_client.upload_file(
        entity_id=task_result.id,
        entity_type=TaskResult,
        file_path=emodel_summary_file,
        file_content_type=ContentType.application_json,
        asset_label=AssetLabel.emodel_analysis_summary,
    )
    L.info("TaskResult registered: %s", task_result.id)

    # --- Upload additional assets needed by task3 (export + validation) ---
    upload_optimization_assets(coord_root, task_result.id)

    # --- Collect ion channel model entities ---
    references = config.parameters_selection.ion_channel_model_references
    ion_channel_models = [
        cast("IonChannelModel", reference.entity(db_client=db_client)) for reference in references
    ]

    # --- Register draft EModel via helper ---
    # Standalone HOC export is not produced; SONATA may still contain a HOC asset.
    sonata_dir = coord_root / "export_emodels_sonata"
    hoc_file = next(sonata_dir.rglob("*.hoc"), None) if sonata_dir.exists() else None
    emodel_entity = register_emodel(
        client=db_client,
        name=f"{emodel_name}",
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
        lifecycle_status=EntityLifecycleStatus.active,
        etype_class=etype_class,
        hoc_file=hoc_file,  # ty:ignore[invalid-argument-type]
        emodel_summary_file=emodel_summary_file,
        electrical_cell_recording_ids=trace_ids or [],
        # entitysdk's figure upload drops the file extension (file_name=<short
        # name>) and current entitycore rejects it with 422 — figure
        # ValidationResults are registered below via
        # register_emodel_figure_validation_results instead.
        validation_result_figure_files=[],
        validation_result_status=False,
    )
    L.info("Draft EModel registered: %s", emodel_entity.id)
    register_emodel_figure_validation_results(
        db_client,
        str(emodel_entity.id),
        validation_figures,
        authorized_public=authorized_public,
    )

    # --- Register draft MEModel via helper ---
    memodel_entity = register_memodel(
        client=db_client,
        name=f"{emodel_name} MEModel",
        description=f"Draft MEModel from optimisation (emodel={emodel_name}).",
        species=species_entity,
        brain_region=brain_region_entity,
        license=license_entity,
        morphology=morph_entity,
        emodel=emodel_entity,
        threshold_current=em_metrics["threshold_current"],
        holding_current=em_metrics["holding_current"],
        authorized_public=authorized_public,
        validation_status=validation_status,
        lifecycle_status=EntityLifecycleStatus.active,
    )
    L.info("Draft MEModel registered: %s", memodel_entity.id)

    memodel_id = str(memodel_entity.id)
    generated_ids = [str(task_result.id), str(emodel_entity.id), memodel_id]

    # --- MEModel calibration/validation results (computed pre-registration) ---
    if calibration is not None:
        calibration_id = register_calibration_result(
            db_client, memodel_id, calibration, authorized_public=authorized_public
        )
        if calibration_id is not None:
            generated_ids.append(calibration_id)
    if validation is not None:
        generated_ids.extend(
            register_memodel_validation_results(
                db_client,
                memodel_id,
                validation,
                authorized_public=authorized_public,
                details_dir=coord_root / "validation_details" / memodel_id,
            )
        )

    # --- Update TaskActivity with generated_ids ---
    if execution_activity_id is not None:
        db_sdk.update_execution_activity_with_generated(
            client=db_client,
            execution_activity_id=UUID(execution_activity_id),
            generated_ids=generated_ids,
        )

    return RegisteredOptimizationOutputs(
        task_result_id=str(task_result.id),
        emodel_id=str(emodel_entity.id),
        memodel_id=memodel_id,
        authorized_public=authorized_public,
        generated_ids=generated_ids,
    )


def register_calibration_result(
    db_client: entitysdk.Client,
    memodel_id: str,
    calibration_dict: dict,
    *,
    authorized_public: bool,
) -> str | None:
    """Register a ``MEModelCalibrationResult`` for the MEModel.

    Skips registration if a calibration result already exists for this MEModel.

    Returns:
        The registered entity ID, or ``None`` if it already existed.
    """
    existing = db_client.search_entity(
        entity_type=MEModelCalibrationResult,
        query={"calibrated_entity_id": memodel_id},
    ).first()
    if existing is not None:
        L.info("MEModelCalibrationResult already exists for %s; skipping.", memodel_id)
        return None

    calibration = MEModelCalibrationResult(
        holding_current=calibration_dict["holding_current"],
        threshold_current=calibration_dict["rheobase"],
        rin=calibration_dict.get("rin"),
        calibrated_entity_id=UUID(memodel_id),
        authorized_public=authorized_public,
    )
    registered = db_client.register_entity(entity=calibration)
    L.info("MEModelCalibrationResult registered: %s (memodel=%s)", registered.id, memodel_id)
    return str(registered.id)


_FIGURE_CONTENT_TYPES = {
    ".pdf": ContentType.application_pdf,
    ".png": ContentType.image_png,
}


def register_memodel_validation_results(
    db_client: entitysdk.Client,
    memodel_id: str,
    validation_dict: dict,
    *,
    authorized_public: bool,
    details_dir: Path,
) -> list[str]:
    """Register ``ValidationResult`` entities for a bluecellulab validation run.

    One ``ValidationResult`` per test entry in ``validation_dict``; figure
    (``.pdf``/``.png``) and ``validation_details`` text are uploaded as assets.
    Entries already registered for ``memodel_id`` are skipped.

    Returns:
        IDs of newly registered ``ValidationResult`` entities.
    """
    details_dir.mkdir(parents=True, exist_ok=True)
    registered_ids: list[str] = []

    for value in validation_dict.values():
        if not isinstance(value, dict) or "name" not in value:
            continue

        existing = db_client.search_entity(
            entity_type=ValidationResult,
            query={"name": value["name"], "validated_entity_id": memodel_id},
        ).first()
        if existing is not None:
            L.info(
                "ValidationResult '%s' already exists for %s; skipping.",
                value["name"],
                memodel_id,
            )
            continue

        validation_result = db_client.register_entity(
            entity=ValidationResult(
                name=value["name"],
                passed=bool(value["passed"]),
                validated_entity_id=UUID(memodel_id),
                authorized_public=authorized_public,
            )
        )
        registered_ids.append(str(validation_result.id))
        L.info(
            "ValidationResult registered: %s (name='%s', passed=%s)",
            validation_result.id,
            value["name"],
            value["passed"],
        )

        for figure in value.get("figures", []):
            figure_path = Path(figure)
            content_type = _FIGURE_CONTENT_TYPES.get(figure_path.suffix)
            if not figure_path.exists():
                L.warning("Validation figure not found: %s", figure_path)
                continue
            if content_type is None:
                L.warning("Unsupported validation figure format: %s", figure_path)
                continue
            db_client.upload_file(
                entity_id=validation_result.id,
                entity_type=ValidationResult,
                file_path=figure_path,
                file_content_type=content_type,
                asset_label=AssetLabel.validation_result_figure,
            )

        details_text = value.get("validation_details")
        if details_text:
            details_path = details_dir / f"{value['name'].replace(' ', '')}_details.txt"
            details_path.write_text(details_text, encoding="utf-8")
            db_client.upload_file(
                entity_id=validation_result.id,
                entity_type=ValidationResult,
                file_path=details_path,
                file_content_type=ContentType.text_plain,
                asset_label=AssetLabel.validation_result_details,
            )

    return registered_ids


def detect_validation_result_name(figure_stem: str) -> str | None:
    """Map a BluePyEModel figure stem to a short ValidationResult name.

    Mirrors entitysdk's naming: the suffix after the last ``__`` separator is
    matched against ``SUFFIX_TO_NAME`` (``thumbnail`` maps to ``None`` → skip).
    """
    suffix_part = figure_stem.rsplit("__", maxsplit=1)[-1]
    for suffix, name in SUFFIX_TO_NAME.items():
        if suffix_part == suffix or suffix_part.startswith(suffix + "."):
            return name
    return None


def register_emodel_figure_validation_results(
    db_client: entitysdk.Client,
    emodel_id: str,
    figure_files: list[Path],
    *,
    authorized_public: bool,
) -> list[str]:
    """Register figure-based ``ValidationResult`` entities for the EModel.

    Workaround for an entitysdk bug: ``register_validation_result_figure``
    uploads with ``file_name=<detected name>`` (no extension), which entitycore
    rejects because the asset suffix must match the declared content type. This
    registers the same entities (name = figure stem, ``passed=False``) but keeps
    the real filename on upload. Remove once fixed upstream.

    Returns:
        IDs of newly registered ``ValidationResult`` entities.
    """
    registered_ids: list[str] = []
    for figure_file in figure_files:
        if detect_validation_result_name(figure_file.stem) is None:
            continue
        content_type = _FIGURE_CONTENT_TYPES.get(figure_file.suffix)
        if content_type is None:
            L.warning("Unsupported figure format: %s", figure_file)
            continue
        validation_result = db_client.register_entity(
            entity=ValidationResult(
                name=figure_file.stem,
                passed=False,
                validated_entity_id=UUID(emodel_id),
                authorized_public=authorized_public,
            )
        )
        db_client.upload_file(
            entity_id=validation_result.id,
            entity_type=ValidationResult,
            file_path=figure_file,
            file_content_type=content_type,
            asset_label=AssetLabel.validation_result_figure,
        )
        registered_ids.append(str(validation_result.id))
        L.info(
            "EModel figure ValidationResult registered: %s (name='%s')",
            validation_result.id,
            figure_file.stem,
        )
    return registered_ids
