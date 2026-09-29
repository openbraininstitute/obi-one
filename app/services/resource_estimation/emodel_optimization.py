"""Resource estimation for emodel optimisation tasks.

Optimisation always runs on one cluster instance; the estimator only adjusts the
timelimit. Wall time scales with ``offspring_size x max_ngen`` evaluations and the
number of protocols per evaluation.
"""

from http import HTTPStatus

import entitysdk

from app.errors import ApiError, ApiErrorCode
from app.schemas.task import LaunchableTaskDefinition, Resources, TaskLaunchSubmit
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.estimate import (
    count_feature_protocols,
    count_morphology_compartments,
    estimate_optimization_workload,
    load_optimization_single_config,
)


def estimate_task_resources(
    json_model: TaskLaunchSubmit,
    db_client: entitysdk.Client,
    task_definition: LaunchableTaskDefinition,
    compute_cell: str,
) -> Resources:
    """Estimate cluster resources for an emodel optimisation task."""
    try:
        config = load_optimization_single_config(
            db_client=db_client, config_id=json_model.config_id
        )
        workload = estimate_optimization_workload(
            offspring_size=config.optimization_params.offspring_size,  # ty:ignore[invalid-argument-type]
            max_ngen=config.optimization_settings.max_ngen,  # ty:ignore[invalid-argument-type]
            n_protocols=count_feature_protocols(db_client=db_client, config=config),
            n_compartments=count_morphology_compartments(db_client=db_client, config=config),
            optimisation_timeout=config.optimization_settings.optimisation_timeout,  # ty:ignore[invalid-argument-type]
        )
    except ValueError as e:
        raise ApiError(
            message=f"Cannot estimate emodel optimisation resources: {e}",
            error_code=ApiErrorCode.RESOURCE_ESTIMATION_ERROR,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        ) from e

    return task_definition.resources.model_copy(
        update={
            "timelimit": workload.timelimit,
            "compute_cell": compute_cell,
        }
    )
