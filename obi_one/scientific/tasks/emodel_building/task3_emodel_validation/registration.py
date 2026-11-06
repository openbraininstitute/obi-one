"""Entity registration for Task 3 e-model validation outputs.

Registers one ``TaskResult`` holding the run summary and figures, an overall
``ValidationResult`` and one ``ValidationResult`` per validation protocol, all
validated against the EModel.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import entitysdk
from entitysdk.models import TaskActivity, TaskResult
from entitysdk.registration.validation_result import FIGURE_EXT_TO_CONTENT_TYPE
from entitysdk.types import AssetLabel, ContentType, TaskResultType

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
    config: EModelValidationSingleConfig, *, uses_optimisation_targets: bool
) -> str:
    """Suffix distinguishing Task 3 validation results from Task 2's and from each other.

    ``register_validation_result`` skips results whose name already exists on the
    EModel. Task 2 registers the un-suffixed names, so every Task 3 run is marked
    ``validation`` plus each target or setting that differs from the defaults.
    """
    settings = config.settings
    parts = ["validation"]
    if not uses_optimisation_targets:
        parts.append(f"extraction {config.target_efeatures.task_result.id_str[:8]}")
    if settings.validation_protocols_only:
        parts.append("validation protocols only")
    if settings.validation_function != FROM_OPTIMISATION:
        parts.append(settings.validation_function)
    if settings.validation_threshold is not None:
        parts.append(f"threshold {settings.validation_threshold:g}")
    return f" [{', '.join(parts)}]"


def figure_files(figures_dir: Path) -> list[Path]:
    """Return the uploadable figure files produced by the validation run."""
    if not figures_dir.exists():
        return []
    return [p for p in sorted(figures_dir.rglob("*")) if p.suffix in FIGURE_EXT_TO_CONTENT_TYPE]


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
            entity_id=execution_activity_id,  # ty:ignore[invalid-argument-type]
            entity_type=TaskActivity,
        )
        authorized_public = getattr(activity, "authorized_public", False)

    emodel = staged.provenance.emodel
    figures = figure_files(figures_dir)
    summary_text = json.dumps(summary, indent=2)
    suffix = result_name_suffix(
        config,
        uses_optimisation_targets=uses_optimisation_targets(config, staged.provenance.config),
    )

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

    generated_ids.extend(
        register_validation_results(
            client=db_client,
            summary=summary,
            validated_entity_id=emodel.id,
            authorized_public=authorized_public,
            name_suffix=suffix,
            figure_files=figures,
        )
    )

    if execution_activity_id is not None:
        db_sdk.update_execution_activity_with_generated(
            client=db_client,
            execution_activity_id=UUID(execution_activity_id),
            generated_ids=generated_ids,
        )
    return RegisteredValidationOutputs(
        task_result_id=str(task_result.id), generated_ids=generated_ids
    )
