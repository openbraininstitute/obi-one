"""Workload and cost estimation for the emodel optimisation stage.

Shared by the launch-time resource estimator (timelimit) and the accounting
count (core-hours), so both derive from the same model of the job.
"""

import json
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

import entitysdk
from entitysdk import models
from entitysdk.types import AssetLabel

from obi_one import deserialize_obi_object_from_json_data
from obi_one.db_sdk import db_sdk

if TYPE_CHECKING:
    # Requires the optional ``emodel`` extra; only imported when installed.
    from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (
        EModelOptimizationSingleConfig,
    )

# Assumed cores on the cell_a "large" cluster instance. The real pool size lives in
# launch-system deployment settings, not in code; verify on staging.
CORES_PER_INSTANCE = 96
# Staging, params/recipe compilation and mechanism compilation before evaluations start.
OVERHEAD_S = 600.0
SAFETY_FACTOR = 1.5
# Seed constants for the wall time of one protocol simulation per evaluation.
# To be refit against the timing log lines reported by the task.
T_SIM_S_BASE = 2.0
T_SIM_S_PER_1K_COMPARTMENTS = 1.0
# Floor matching the task-definition default timelimit (02:00).
DEFAULT_TIMELIMIT_S = 2 * 3600.0
# Hard cap on the launch timelimit; larger estimates are rejected.
MAX_TIMELIMIT_S = 24 * 3600.0


@dataclass(frozen=True)
class OptimizationWorkload:
    """Derived launch parameters for one optimisation job."""

    used_cores: int
    n_waves: int
    wall_seconds: float
    timelimit_seconds: float

    @property
    def timelimit(self) -> str:
        """Timelimit in launch-system ``HH:MM`` format."""
        total_minutes = math.ceil(self.timelimit_seconds / 60)
        return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"

    @property
    def count(self) -> int:
        """Accounting count: estimated core-hours, minimum 1."""
        return max(1, math.ceil(self.used_cores * self.timelimit_seconds / 3600))


def estimate_optimization_workload(
    *,
    offspring_size: int,
    max_ngen: int,
    n_protocols: int,
    n_compartments: int,
    optimisation_timeout: float | None = None,
) -> OptimizationWorkload:
    """Estimate core usage and wall time for one optimisation job.

    Evaluations within a generation run in parallel, so one seed can use at most
    ``offspring_size`` cores; when the offspring exceeds the instance, generations
    run in ``n_waves`` waves. ``optimisation_timeout`` caps the per-evaluation
    simulation time.
    """
    used_cores = min(CORES_PER_INSTANCE, offspring_size)
    n_waves = math.ceil(offspring_size / used_cores)

    t_eval_s = n_protocols * (T_SIM_S_BASE + T_SIM_S_PER_1K_COMPARTMENTS * n_compartments / 1000)
    if optimisation_timeout is not None:
        t_eval_s = min(t_eval_s, optimisation_timeout)

    wall_seconds = OVERHEAD_S + (max_ngen + 1) * n_waves * t_eval_s
    timelimit_seconds = max(DEFAULT_TIMELIMIT_S, wall_seconds * SAFETY_FACTOR)
    if timelimit_seconds > MAX_TIMELIMIT_S:
        msg = (
            f"Estimated optimisation wall time ({timelimit_seconds / 3600:.1f} h) exceeds the "
            f"maximum timelimit ({MAX_TIMELIMIT_S / 3600:.0f} h) for "
            f"offspring_size={offspring_size}, max_ngen={max_ngen}, n_protocols={n_protocols}."
        )
        raise ValueError(msg)
    return OptimizationWorkload(
        used_cores=used_cores,
        n_waves=n_waves,
        wall_seconds=wall_seconds,
        timelimit_seconds=timelimit_seconds,
    )


def load_optimization_single_config(
    *,
    db_client: entitysdk.Client,
    config_id: UUID,
) -> "EModelOptimizationSingleConfig":
    """Download and deserialize the emodel optimisation task config."""
    from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (  # ruff: ignore[import-outside-top-level]
        EModelOptimizationSingleConfig,
    )

    task_config = db_client.get_entity(entity_id=config_id, entity_type=models.TaskConfig)
    config_asset = db_sdk.get_entity_asset_by_label(
        client=db_client,
        config=task_config,
        asset_label=AssetLabel.task_config,
    )
    config_bytes = db_client.download_content(
        entity_id=config_id,
        entity_type=models.TaskConfig,
        asset_id=config_asset.id,
    )
    return EModelOptimizationSingleConfig.model_validate(
        deserialize_obi_object_from_json_data(json.loads(config_bytes.decode("utf-8"))).model_dump()
    )


def count_feature_protocols(
    *,
    db_client: entitysdk.Client,
    config: "EModelOptimizationSingleConfig",
) -> int:
    """Count protocols in the task-1 extracted-features JSON.

    The fitness-calculator config groups features under ``protocols``; when that
    key is absent, protocol names are recovered from ``efeatures`` keys of the
    form ``<protocol>.<location>.<feature>``.
    """
    tr_entity = config.initialize.target_efeatures.entity(db_client=db_client)
    features_asset = db_sdk.get_entity_asset_by_label(
        client=db_client,
        config=tr_entity,
        asset_label=AssetLabel.efeature_extraction_features,
    )
    features = json.loads(
        db_client.download_content(
            entity_id=tr_entity.id,
            entity_type=models.TaskResult,
            asset_id=features_asset.id,
        ).decode("utf-8")
    )
    n_protocols = 0
    for entry in features.values():
        if not isinstance(entry, dict):
            continue
        fcc = entry.get("fitness_calculator_configuration", entry)
        protocols = fcc.get("protocols")
        if isinstance(protocols, dict):
            n_protocols += len(protocols)
            continue
        efeatures = fcc.get("efeatures")
        if isinstance(efeatures, dict):
            n_protocols += len({key.split(".")[0] for key in efeatures})
    if n_protocols == 0:
        msg = (
            f"Extracted-features asset of TaskResult {tr_entity.id} contains no protocols; "
            "cannot estimate resources."
        )
        raise ValueError(msg)
    return n_protocols


def count_morphology_compartments(
    *,
    db_client: entitysdk.Client,
    config: "EModelOptimizationSingleConfig",
) -> int:
    """Approximate compartment count from the staged SWC asset (one point per line)."""
    swc_content = config.initialize.morphology.swc_file_content(db_client=db_client)
    return sum(1 for line in swc_content.splitlines() if line.strip() and not line.startswith("#"))


def estimate_emodel_optimization_count(*, db_client: entitysdk.Client, config_id: UUID) -> int:
    """Estimate the accounting count (core-hours) for an emodel optimisation job."""
    config = load_optimization_single_config(db_client=db_client, config_id=config_id)
    workload = estimate_optimization_workload(
        offspring_size=config.optimization_params.offspring_size,  # ty:ignore[invalid-argument-type]
        max_ngen=config.optimization_settings.max_ngen,  # ty:ignore[invalid-argument-type]
        n_protocols=count_feature_protocols(db_client=db_client, config=config),
        n_compartments=count_morphology_compartments(db_client=db_client, config=config),
        optimisation_timeout=config.optimization_settings.optimisation_timeout,  # ty:ignore[invalid-argument-type]
    )
    return workload.count
