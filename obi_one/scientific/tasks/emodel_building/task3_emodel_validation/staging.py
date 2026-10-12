"""Working-directory staging for the BluePyEModel e-model validation stage.

Resolves the optimisation that produced an EModel through EntityCore provenance and
rebuilds its BluePyEModel working directory (features, exemplar morphology, mechanisms,
params/recipes, ``final.json``) so the optimised parameters can be scored, optionally
against other targets.
"""

import dataclasses
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import entitysdk
from bluepyemodel.preprocessing import NormalizedIonChannelModel, preflight_morphology
from bluepyemodel.tools.utils import are_same_protocol
from entitysdk.models import EModel, TaskActivity, TaskConfig, TaskResult
from entitysdk.types import AssetLabel, EntityType, TaskActivityType, TaskResultType

from obi_one.core.deserialize import deserialize_obi_object_from_json_data
from obi_one.db_sdk import db_sdk
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization import (
    staging as optimisation_staging,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (
    EModelOptimizationSingleConfig,
)
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.utils import (
    resolve_ion_channel_models,
)
from obi_one.scientific.tasks.emodel_building.task3_emodel_validation.blocks import (
    FROM_OPTIMISATION,
)
from obi_one.scientific.tasks.emodel_building.task3_emodel_validation.config import (
    EModelValidationSingleConfig,
)
from obi_one.scientific.tasks.emodel_building.validation_scoring import (
    ResolvedValidationSettings,
    flagged_validation_protocols,
)

L = logging.getLogger(__name__)


@dataclass(frozen=True)
class OptimisationProvenance:
    """Entities of the optimisation run that produced the validated EModel."""

    emodel: EModel
    config: EModelOptimizationSingleConfig
    task_result: TaskResult


@dataclass(frozen=True)
class StagedValidation:
    """Everything the validation run needs from the staged working directory."""

    provenance: OptimisationProvenance
    settings: ResolvedValidationSettings
    final_entry: dict
    normalized_models: dict[str, NormalizedIonChannelModel]


def resolve_optimisation_provenance(
    emodel_id: str,
    db_client: entitysdk.client.Client,
) -> OptimisationProvenance:
    """Find the optimisation execution activity, its TaskConfig and its TaskResult."""
    emodel = db_client.get_entity(entity_id=UUID(emodel_id), entity_type=EModel)
    activity = db_client.search_entity(
        entity_type=TaskActivity,
        query={
            "generated__id": emodel.id,
            "task_activity_type": TaskActivityType.emodel_optimization__execution,
        },
    ).first()
    if activity is None:
        msg = (
            f"EModel {emodel_id} has no generating "
            f"'{TaskActivityType.emodel_optimization__execution}' activity; only e-models "
            "optimised on the platform can be validated."
        )
        raise ValueError(msg)

    task_config_ids = [e.id for e in activity.used or [] if e.type == EntityType.task_config]
    if len(task_config_ids) != 1:
        msg = (
            f"Expected one TaskConfig used by activity {activity.id}, found {len(task_config_ids)}."
        )
        raise ValueError(msg)
    task_config = db_client.get_entity(entity_id=task_config_ids[0], entity_type=TaskConfig)
    config_json = db_sdk.select_json_asset_content(
        client=db_client,
        entity=task_config,
        selection={"label": AssetLabel.task_config},
    )
    config = deserialize_obi_object_from_json_data(config_json)
    if not isinstance(config, EModelOptimizationSingleConfig):
        msg = f"TaskConfig {task_config.id} is not an EModelOptimizationSingleConfig."
        raise TypeError(msg)

    task_results = [
        db_client.get_entity(entity_id=e.id, entity_type=TaskResult)
        for e in activity.generated or []
        if e.type == EntityType.task_result
    ]
    task_result = next(
        (
            tr
            for tr in task_results
            if tr.task_result_type == TaskResultType.emodel_optimization__result
        ),
        None,
    )
    if task_result is None:
        msg = f"Activity {activity.id} generated no emodel_optimization__result TaskResult."
        raise ValueError(msg)

    return OptimisationProvenance(emodel=emodel, config=config, task_result=task_result)


def stage_final_entry(
    provenance: OptimisationProvenance,
    coord_root: Path,
    db_client: entitysdk.client.Client,
) -> dict:
    """Write a ``final.json`` holding only the optimised model of the EModel's seed.

    The optimisation TaskResult stores BluePyEModel's ``final.json`` as its
    ``emodel_analysis_summary``. Previous validation results are cleared so the
    entry is re-scored from scratch.
    """
    download_dir = coord_root / "optimisation_summary"
    path = db_sdk.fetch_asset_by_label(
        client=db_client,
        entity=provenance.task_result,
        asset_label=AssetLabel.emodel_analysis_summary,
        output_path=download_dir,
    )
    final = json.loads(Path(path).read_text(encoding="utf-8"))
    emodel_name = provenance.config.initialize.emodel
    seed = int(provenance.emodel.seed)
    key, entry = next(
        (
            (k, v)
            for k, v in final.items()
            if isinstance(v, dict) and v.get("emodel") == emodel_name and v.get("seed") == seed
        ),
        (None, None),
    )
    if entry is None:
        msg = f"No final.json entry for emodel={emodel_name!r}, seed={seed}."
        raise ValueError(msg)

    entry = {**entry, "validation_fitness": {}, "validated": None}
    (coord_root / "final.json").write_text(json.dumps({key: entry}, indent=2), encoding="utf-8")
    L.info("Staged final.json entry %s", key)
    return entry


THRESHOLD_SEARCH_PROTOCOL_TYPES = {"ThresholdBasedProtocol", "LocalThresholdBasedProtocol"}
THRESHOLD_PROTOCOL_TYPES = {*THRESHOLD_SEARCH_PROTOCOL_TYPES, "ThresholdBasedNoHoldingProtocol"}


def check_threshold_search_targets(features_path: Path) -> None:
    """Require the RMP/Rin/holding targets that threshold-based protocols need.

    Threshold-based protocols are scaled by BluePyEModel's holding and threshold current
    search, which uses e-features stored under the ``RMPProtocol``, ``RinProtocol`` and
    (with holding current) ``SearchHoldingCurrent`` pre-protocols of the features file.
    """
    data = json.loads(features_path.read_text(encoding="utf-8"))
    types = {p.get("protocol_type") for p in data.get("protocols", [])}
    if not types & THRESHOLD_PROTOCOL_TYPES:
        return
    required = {"RMPProtocol", "RinProtocol"}
    if types & THRESHOLD_SEARCH_PROTOCOL_TYPES:
        required.add("SearchHoldingCurrent")
    present = {f.get("protocol_name") for f in data.get("efeatures", [])}
    missing = sorted(required - present)
    if missing:
        msg = (
            "The target e-features have threshold-based protocols but no e-features for "
            f"{missing}; extract them with RMP and Rin protocols set."
        )
        raise ValueError(msg)


def protocol_names(features_path: Path) -> list[str]:
    """Return the protocol names of a fitness-calculator configuration file."""
    data = json.loads(features_path.read_text(encoding="utf-8"))
    return [p["name"] for p in data.get("protocols", []) if "name" in p]


def mark_validation_protocols(features_path: Path, validation_protocols: list[str]) -> None:
    """Align each protocol's ``validation`` flag with the chosen validation protocols."""
    data = json.loads(features_path.read_text(encoding="utf-8"))
    for protocol in data.get("protocols", []):
        protocol["validation"] = any(
            are_same_protocol(protocol.get("name"), name) for name in validation_protocols
        )
    features_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def uses_optimisation_targets(
    config: EModelValidationSingleConfig,
    optimisation_config: EModelOptimizationSingleConfig,
) -> bool:
    """Whether the selected targets are the extraction the e-model was optimised on."""
    return (
        config.target_efeatures.task_result.id_str
        == optimisation_config.target_efeatures.task_result.id_str
    )


def resolve_settings(
    config: EModelValidationSingleConfig,
    optimisation_config: EModelOptimizationSingleConfig,
    features_path: Path,
) -> ResolvedValidationSettings:
    """Fill unset validation settings from the optimisation configuration or targets."""
    settings = config.settings
    optimisation_settings = optimisation_config.optimization_settings

    validation_protocols = settings.validation_protocols
    if not validation_protocols:
        if not uses_optimisation_targets(config, optimisation_config):
            validation_protocols = protocol_names(features_path)
        else:
            validation_protocols = list(
                optimisation_settings.validation_protocols
            ) or flagged_validation_protocols(features_path)
    if settings.validation_protocols_only and not validation_protocols:
        msg = "validation_protocols_only is set but there are no validation protocols to score."
        raise ValueError(msg)

    validation_function = (
        optimisation_settings.validation_function
        if settings.validation_function == FROM_OPTIMISATION
        else settings.validation_function
    )
    validation_threshold = (
        settings.validation_threshold
        if settings.validation_threshold is not None
        else optimisation_settings.validation_threshold
    )
    return ResolvedValidationSettings(
        validation_protocols=list(validation_protocols),
        validation_protocols_only=settings.validation_protocols_only,
        validation_function=str(validation_function),
        validation_threshold=float(validation_threshold),  # ty:ignore[invalid-argument-type]
    )


def stage_working_directory(
    config: EModelValidationSingleConfig,
    coord_root: Path,
    db_client: entitysdk.client.Client,
) -> StagedValidation:
    """Rebuild the optimisation's BluePyEModel working directory for validation.

    The morphology is always the optimisation's exemplar, so the result describes the
    validated EModel itself.
    """
    provenance = resolve_optimisation_provenance(config.emodel.emodel.id_str, db_client)
    optimisation_config = provenance.config

    features_path = optimisation_staging.download_extraction_features(
        optimisation_config, config.target_efeatures.task_result, coord_root, db_client
    )
    check_threshold_search_targets(features_path)

    morph_filename = optimisation_staging.stage_morphology(
        optimisation_config, coord_root, db_client
    )
    morphology_capabilities = preflight_morphology(
        coord_root / "morphologies" / morph_filename,
        optimisation_config.morphology_settings.axon_modifier,
    )
    optimisation_staging.stage_mechanisms(optimisation_config, coord_root, db_client)

    normalized_models = resolve_ion_channel_models(
        optimisation_config.parameters_selection.ion_channel_model_references,
        db_client,
    )
    artifacts = optimisation_staging.build_artifacts(
        optimisation_config,
        db_client=db_client,
        mtype=optimisation_staging.derive_mtype(optimisation_config, db_client),
        morph_filename=morph_filename,
        morphology_capabilities=morphology_capabilities,
        normalized_models=normalized_models,
    )

    settings = resolve_settings(config, optimisation_config, features_path)
    mark_validation_protocols(features_path, settings.validation_protocols)
    recipes = json.loads(json.dumps(artifacts.recipes))
    pipeline_settings = recipes[optimisation_config.initialize.emodel].setdefault(
        "pipeline_settings", {}
    )
    pipeline_settings.update(
        {
            "validation_protocols": settings.validation_protocols,
            "validation_function": settings.validation_function,
            "validation_threshold": settings.validation_threshold,
        }
    )
    dataclasses.replace(artifacts, recipes=recipes).write(coord_root)

    final_entry = stage_final_entry(provenance, coord_root, db_client)
    return StagedValidation(
        provenance=provenance,
        settings=settings,
        final_entry=final_entry,
        normalized_models=normalized_models,
    )
