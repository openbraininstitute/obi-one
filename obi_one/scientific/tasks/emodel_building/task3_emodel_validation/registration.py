"""Entity registration for Task 3 e-model validation outputs.

Registers one ``TaskResult`` holding the run summary and figures, an overall
``ValidationResult`` and one ``ValidationResult`` per validation protocol, all
validated against the EModel. The ValidationResults overwrite earlier ones of the same
name, so the EModel carries the latest verdict (see :func:`result_name_suffix`).
"""

import json
import logging
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from uuid import UUID

import entitysdk
from entitysdk.exception import EntitySDKError
from entitysdk.models import EModel, TaskActivity, TaskResult
from entitysdk.registration.validation_result import FIGURE_EXT_TO_CONTENT_TYPE
from entitysdk.types import AssetLabel, ContentType, TaskResultType

from obi_one.core.exception import OBIONEError
from obi_one.db_sdk import db_sdk
from obi_one.scientific.tasks.emodel_building.task3_emodel_validation.blocks import (
    FROM_OPTIMISATION,
)
from obi_one.scientific.tasks.emodel_building.task3_emodel_validation.config import (
    EModelValidationSingleConfig,
)
from obi_one.scientific.tasks.emodel_building.task3_emodel_validation.staging import (
    StagedValidation,
    uses_optimisation_targets,
)
from obi_one.scientific.tasks.emodel_building.validation_scoring import (
    register_validation_results,
)

L = logging.getLogger(__name__)

SUMMARY_FILENAME = "emodel_validation_summary.txt"


@dataclass(frozen=True)
class RegisteredValidationOutputs:
    """IDs of entities registered after a validation run."""

    task_result_id: str
    generated_ids: list[str]


def result_name_suffix(
    config: EModelValidationSingleConfig,
    *,
    uses_optimisation_targets: bool,
    mark_validation: bool = False,
) -> str:
    """Suffix naming the targets and settings of a Task 3 run that differ from the defaults.

    Results are overwritten by name, so the latest run replaces the earlier ones of the
    same name. A run with the optimisation's own targets and default settings has no
    suffix: it replaces Task 2's results, and the EModel shows the latest verdict. Any
    other run is suffixed with what differs and replaces only its own earlier run.
    ``mark_validation`` adds ``validation``, for results that must not replace
    Task 2's (see :func:`register_output_entities`).
    """
    settings = config.settings
    parts = ["validation"] if mark_validation else []
    if not uses_optimisation_targets:
        parts.append(f"extraction {config.target_efeatures.task_result.id_str[:8]}")
    if settings.validation_protocols_only:
        parts.append("validation protocols only")
    if settings.validation_function != FROM_OPTIMISATION:
        parts.append(settings.validation_function)
    if settings.validation_threshold is not None:
        parts.append(f"threshold {settings.validation_threshold:g}")
    return f" [{', '.join(parts)}]" if parts else ""


def is_forbidden(error: EntitySDKError) -> bool:
    """Whether an entitysdk error comes from an HTTP 403 (another user's entity)."""
    response = getattr(error.__cause__, "response", None)
    return getattr(response, "status_code", None) == HTTPStatus.FORBIDDEN


def figure_files(figures_dir: Path) -> list[Path]:
    """Return the uploadable figure files produced by the validation run."""
    if not figures_dir.exists():
        return []
    return [p for p in sorted(figures_dir.rglob("*")) if p.suffix in FIGURE_EXT_TO_CONTENT_TYPE]


def sync_emodel_output_verdict(
    db_client: entitysdk.Client,
    emodel: EModel,
    summary: dict,
    work_dir: Path,
) -> None:
    """Refresh the validation verdict on the EModel's optimisation output asset.

    ``emodel_optimization_output`` records the verdict of the optimisation-time
    validation; a re-validation run supersedes it, so ``passedValidation`` and
    ``scoreValidation`` are rewritten with the latest summary. A missing asset
    is reported but not fatal — the authoritative verdicts are the registered
    ``ValidationResult`` entities.
    """
    from bluepyemodel.emodel_pipeline.emodel import (  # ruff: ignore[import-outside-top-level]
        format_dict_for_resource,
    )

    try:
        asset = db_sdk.get_entity_asset_by_label(
            client=db_client,
            config=emodel,
            asset_label=AssetLabel.emodel_optimization_output,
        )
    except OBIONEError:
        L.warning(
            "EModel %s has no emodel_optimization_output asset; the validation verdict "
            "was registered on the ValidationResults only.",
            emodel.id,
        )
        return

    data = json.loads(
        db_client.download_content(entity_id=emodel.id, entity_type=EModel, asset_id=asset.id)
    )
    score_validation = {
        feature_name: feature["score"]
        for protocol in summary["protocols"].values()
        if protocol.get("validation")
        for feature_name, feature in protocol.get("features", {}).items()
    }
    data["passedValidation"] = bool(summary["passed"])
    data["scoreValidation"] = format_dict_for_resource(score_validation)

    updated_path = work_dir / Path(asset.path).name
    updated_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    db_client.update_asset_file(
        entity_id=emodel.id,
        entity_type=EModel,
        asset_id=asset.id,
        file_path=updated_path,
        file_content_type=ContentType.application_json,
    )
    L.info(
        "EModel %s optimisation output verdict updated (passedValidation=%s).",
        emodel.id,
        data["passedValidation"],
    )


def register_output_entities(
    config: EModelValidationSingleConfig,
    coord_root: Path,
    db_client: entitysdk.Client,
    *,
    staged: StagedValidation,
    summary: dict,
    figures_dir: Path,
    execution_activity_id: str | None = None,
) -> RegisteredValidationOutputs:
    """Register the TaskResult and ValidationResults of an e-model validation run."""
    authorized_public = False
    if execution_activity_id is not None:
        activity = db_client.get_entity(
            entity_id=UUID(execution_activity_id),
            entity_type=TaskActivity,
        )
        authorized_public = getattr(activity, "authorized_public", False)

    emodel = staged.provenance.emodel
    figures = figure_files(figures_dir)
    summary_text = json.dumps(summary, indent=2)
    optimisation_targets = uses_optimisation_targets(config, staged.provenance.config)
    suffix = result_name_suffix(config, uses_optimisation_targets=optimisation_targets)

    task_result = db_client.register_entity(
        TaskResult(
            name=f"EModel Validation Result — {emodel.name}{suffix}",
            description=f"BluePyEModel score validation of EModel {emodel.id}.",
            authorized_public=authorized_public,
            task_result_type=TaskResultType.optimized_emodel_analysis_validation__result,
        )
    )
    summary_path = coord_root / SUMMARY_FILENAME
    summary_path.write_text(summary_text, encoding="utf-8")
    db_client.upload_file(
        entity_id=task_result.id,
        entity_type=TaskResult,
        file_path=summary_path,
        file_content_type=ContentType.text_plain,
        asset_label=AssetLabel.validation_result_details,
    )
    for figure in figures:
        db_client.upload_file(
            entity_id=task_result.id,
            entity_type=TaskResult,
            file_path=figure,
            file_content_type=FIGURE_EXT_TO_CONTENT_TYPE[figure.suffix],
            asset_label=AssetLabel.validation_result_figure,
        )
    L.info("TaskResult registered: %s", task_result.id)
    generated_ids = [str(task_result.id)]

    results = {
        "client": db_client,
        "summary": summary,
        "validated_entity_id": emodel.id,
        "authorized_public": authorized_public,
        "figure_files": figures,
    }
    try:
        result_ids = register_validation_results(**results, name_suffix=suffix, overwrite=True)
    except EntitySDKError as error:
        if not is_forbidden(error):
            raise
        # The results of that name belong to another user: register this run's next
        # to them, skipping any that the same user already registered.
        fallback = result_name_suffix(
            config, uses_optimisation_targets=optimisation_targets, mark_validation=True
        )
        L.warning(
            "Not allowed to overwrite the ValidationResults of EModel %s; registering "
            "this run's results with the suffix %r instead.",
            emodel.id,
            fallback,
        )
        result_ids = register_validation_results(**results, name_suffix=fallback)
    generated_ids.extend(result_ids)
    if execution_activity_id is not None:
        db_sdk.update_execution_activity_with_generated(
            client=db_client,
            execution_activity_id=UUID(execution_activity_id),
            generated_ids=generated_ids,
        )
    try:
        sync_emodel_output_verdict(db_client, emodel, summary, coord_root)
    except Exception:  # ruff: ignore[blind-except]
        L.exception(
            "Could not update the optimisation output verdict of EModel %s; the verdict "
            "is registered on the ValidationResults.",
            emodel.id,
        )
    return RegisteredValidationOutputs(
        task_result_id=str(task_result.id), generated_ids=generated_ids
    )
