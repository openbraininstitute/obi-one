import time
from datetime import UTC, datetime
from http import HTTPStatus
from uuid import UUID

from entitysdk import Client, ProjectContext, models
from entitysdk.types import CircuitScale
from fastapi import HTTPException
from obp_accounting_sdk import AccountingSessionFactory, OneshotSession
from obp_accounting_sdk.constants import ServiceSubtype
from obp_accounting_sdk.errors import BaseAccountingError, InsufficientFundsError

from app.config import settings
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from app.schemas.accounting import AccountingParameters
from app.schemas.auth import UserContext
from app.schemas.callback import CallBack, HttpRequestCallBackConfig
from app.schemas.task import TaskAccountingInfo, TaskDefinition
from app.types import CallBackAction, CallBackEvent, TaskType

CIRCUIT_SCALE_TO_SERVICE_SUBTYPE = {
    CircuitScale.small: ServiceSubtype.SMALL_SIM,
    CircuitScale.microcircuit: ServiceSubtype.MICROCIRCUIT_SIM,
    CircuitScale.region: ServiceSubtype.REGION_SIM,
    CircuitScale.system: ServiceSubtype.SYSTEM_SIM,
    CircuitScale.whole_brain: ServiceSubtype.WHOLE_BRAIN_SIM,
}


def make_task_reservation(
    *,
    service_subtype: ServiceSubtype,
    user_context: UserContext,
    accounting_parameters: AccountingParameters,
    accounting_factory: AccountingSessionFactory,
) -> OneshotSession:
    accounting_session = accounting_factory.oneshot_session(
        subtype=service_subtype,
        proj_id=user_context.project_id,
        user_id=user_context.subject,
        count=accounting_parameters.count,
    )
    try:
        accounting_session.make_reservation()
        L.info("Accounting reservation success")
    except InsufficientFundsError as ex:
        msg = f"Insufficient funds: {ex}"
        L.warning(msg)
        raise ApiError(
            http_status_code=HTTPStatus.FORBIDDEN,
            error_code=ApiErrorCode.ACCOUNTING_INSUFFICIENT_FUNDS_ERROR,
            message="The project does not have enough funds to run the simulation",
            details=str(ex),
        ) from ex
    except BaseAccountingError as ex:
        L.warning(f"Accounting service error: {ex}")
        raise ApiError(
            http_status_code=HTTPStatus.BAD_GATEWAY,
            error_code=ApiErrorCode.ACCOUNTING_GENERIC_ERROR,
            message="Accounting service error",
            details=str(ex),
        ) from ex

    accounting_job_id = str(accounting_session._job_id)  # noqa: SLF001
    L.info(
        f"Accounting parameters reserved: subtype={service_subtype}, "
        f"count={accounting_parameters.count}, job_id={accounting_job_id}"
    )
    return accounting_session


def estimate_task_cost(
    *,
    db_client: Client,
    config_id: UUID,
    task_definition: TaskDefinition,
    project_context: ProjectContext,
    accounting_factory: AccountingSessionFactory,
) -> TaskAccountingInfo:
    """Estimates the cost and accounting parameters for a task."""
    accounting_parameters = _evaluate_accounting_parameters(
        db_client=db_client,
        config_id=config_id,
        task_definition=task_definition,
    )
    cost_estimate = accounting_factory.estimate_oneshot_cost(
        subtype=task_definition.accounting_service_subtype,
        count=accounting_parameters.count,
        proj_id=str(project_context.project_id),
    )
    return TaskAccountingInfo(
        cost=cost_estimate,
        config_id=config_id,
        parameters=accounting_parameters,
        task_type=task_definition.task_type,
    )


def _evaluate_accounting_parameters(
    *,
    db_client: Client,
    config_id: UUID,
    task_definition: TaskDefinition,
) -> AccountingParameters:
    """Evaluate accounting parameters from the task configuration.

    Returns the service subtype and count needed for cost estimation.
    For Simulation configs, determines the service subtype based on the circuit scale
    and uses the neuron_count from the simulation entity for the count.
    """
    match task_definition.task_type:
        case TaskType.circuit_simulation:
            return _evaluate_circuit_simulation_parameters(
                db_client=db_client,
                simulation_id=config_id,
            )
        case _:
            # For other task types, use the default mapping
            return AccountingParameters(
                count=1,
                service_subtype=task_definition.accounting_service_subtype,
            )


def _evaluate_circuit_simulation_parameters(
    *,
    db_client: Client,
    simulation_id: UUID,
) -> AccountingParameters:
    simulation = db_client.get_entity(
        entity_id=simulation_id,
        entity_type=models.Simulation,
    )
    # TODO: actually use the circuit and simulation files to determine the count
    count = simulation.number_neurons

    circuit = db_client.get_entity(entity_id=simulation.entity_id, entity_type=models.Circuit)

    try:
        service_subtype = CIRCUIT_SCALE_TO_SERVICE_SUBTYPE[circuit.scale]
    except KeyError as e:
        msg = f"Unsupported circuit scale '{circuit.scale}' for cost estimation"
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=msg) from e

    return AccountingParameters(count=count, service_subtype=service_subtype)


def generate_accounting_callbacks(
    accounting_job_id: str,
    service_subtype: ServiceSubtype,
    count: int,
    project_id: str,
) -> list[CallBack]:
    return [
        _generate_accounting_failure_callback(
            accounting_job_id=accounting_job_id,
        ),
        _generate_accounting_success_callback(
            accounting_job_id=accounting_job_id,
            service_subtype=service_subtype,
            count=count,
            project_id=project_id,
        ),
    ]


def _generate_accounting_failure_callback(
    accounting_job_id: str,
) -> CallBack:
    """Builds the callback URL for accounting failure (reservation deletion).

    Points directly to the accounting service DELETE endpoint.
    The job_id is included in the URL path.
    """
    config = HttpRequestCallBackConfig(
        url=f"{settings.ACCOUNTING_BASE_URL}/reservation/oneshot/{accounting_job_id}",
        method="DELETE",
    )
    return CallBack(
        config=config,
        event_type=CallBackEvent.job_on_failure,
        action_type=CallBackAction.http_request_with_token,
    )


def _generate_accounting_success_callback(
    accounting_job_id: str,
    service_subtype: ServiceSubtype,
    count: int,
    project_id: str,
) -> CallBack:
    """Builds the callback URL and payload for accounting success (usage addition).

    Points directly to the accounting service POST /usage/oneshot endpoint.
    """
    config = HttpRequestCallBackConfig(
        url=f"{settings.ACCOUNTING_BASE_URL}/usage/oneshot",
        method="POST",
        payload={
            "type": "oneshot",
            "subtype": service_subtype,
            "proj_id": project_id,
            "job_id": accounting_job_id,
            "count": str(count),
            "timestamp": str(int(time.time())),
        },
    )
    return CallBack(
        config=config,
        event_type=CallBackEvent.job_on_success,
        action_type=CallBackAction.http_request_with_token,
    )
