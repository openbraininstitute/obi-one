from http import HTTPStatus

import entitysdk
from entitysdk import models
from entitysdk.types import CircuitScale

from app.errors import ApiError, ApiErrorCode
from app.schemas.accounting import AccountingParameters
from app.schemas.task import Resources, TaskDefinition, TaskLaunchSubmit

# Scales supported for synapse parameterization. Anything larger than "small" is rejected.
SUPPORTED_CIRCUIT_SCALES = frozenset(
    {CircuitScale.single, CircuitScale.pair, CircuitScale.small, CircuitScale.microcircuit}
)


def estimate_task_resources(
    json_model: TaskLaunchSubmit,
    db_client: entitysdk.Client,
    task_definition: TaskDefinition,
    compute_cell: str,
    accounting_parameters: AccountingParameters | None = None,  # ruff: ignore[unused-function-argument]
) -> Resources:
    """Estimate machine resources for a synapse parameterization task.

    Only guards against oversized parent circuits: a scale larger than ``small`` is
    rejected, otherwise the defaults from TASK_DEFINITIONS are kept.
    """
    config = db_client.get_entity(
        entity_id=json_model.config_id,
        entity_type=models.TaskConfig,
    )

    # Resolve the parent circuit referenced by the config and check its scale.
    if not config.inputs:
        msg = (
            "Synapse parameterization config has no input circuit registered; cannot "
            "check the circuit scale."
        )
        raise ApiError(
            message=msg,
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    circuit_id = config.inputs[0].id
    circuit = db_client.get_entity(entity_id=circuit_id, entity_type=models.Circuit)

    if circuit.scale not in SUPPORTED_CIRCUIT_SCALES:
        supported = ", ".join(
            f"'{scale.value}'" for scale in CircuitScale if scale in SUPPORTED_CIRCUIT_SCALES
        )
        msg = (
            f"Synapse parameterization is not supported for circuits of scale"
            f" '{circuit.scale}'. Supported scales: {supported}."
        )
        raise ApiError(
            message=msg,
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )

    # Keep the defaults defined in TASK_DEFINITIONS.
    return task_definition.resources.model_copy(update={"compute_cell": compute_cell})
