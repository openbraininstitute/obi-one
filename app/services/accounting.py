from http import HTTPStatus
from uuid import UUID

import httpx
from entitysdk import Client, ProjectContext, models
from entitysdk.types import AssetLabel, CircuitScale
from fastapi import HTTPException
from obp_accounting_sdk import AccountingSessionFactory, OneshotSession
from obp_accounting_sdk.constants import ServiceSubtype
from obp_accounting_sdk.errors import BaseAccountingError, InsufficientFundsError
from obp_accounting_sdk.utils import get_current_timestamp

from app.config import settings
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from app.schemas.accounting import AccountingParameters
from app.schemas.auth import UserContext
from app.schemas.callback import CallBack, HttpRequestCallBackConfig
from app.schemas.task import TaskAccountingInfo, TaskDefinition
from app.types import CallBackAction, CallBackEvent, TaskType
from app.utils.http import make_http_request
from obi_one.scientific.tasks.circuit_extraction.estimate import estimate_circuit_extraction_count
from obi_one.scientific.tasks.skeletonization.estimate import estimate_skeletonization_count
from obi_one.utils.db_sdk import select_json_asset_content

CIRCUIT_SCALE_TO_SERVICE_SUBTYPE = {
    CircuitScale.single: ServiceSubtype.SINGLE_SIM,
    CircuitScale.pair: ServiceSubtype.PAIR_SIM,
    CircuitScale.small: ServiceSubtype.SMALL_SIM,
    CircuitScale.microcircuit: ServiceSubtype.MICROCIRCUIT_SIM,
    CircuitScale.region: ServiceSubtype.REGION_SIM,
    CircuitScale.system: ServiceSubtype.SYSTEM_SIM,
    CircuitScale.whole_brain: ServiceSubtype.WHOLE_BRAIN_SIM,
}


def make_task_reservation(
    *,
    user_context: UserContext,
    accounting_parameters: AccountingParameters,
    accounting_factory: AccountingSessionFactory,
) -> OneshotSession:
    accounting_session = accounting_factory.oneshot_session(
        subtype=accounting_parameters.service_subtype,
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

    L.info(
        f"Accounting parameters reserved: subtype={accounting_parameters.service_subtype}, "
        f"count={accounting_parameters.count}, job_id={accounting_session.job_id}"
    )
    return accounting_session  # ty:ignore[invalid-return-type]


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
        subtype=accounting_parameters.service_subtype,
        count=accounting_parameters.count,
        proj_id=str(project_context.project_id),
    )
    L.info(
        f"Estimated cost: subtype={accounting_parameters.service_subtype}, "
        f"count={accounting_parameters.count}, proj_id={project_context.project_id}, "
        f"cost={cost_estimate}"
    )

    return TaskAccountingInfo(
        cost=cost_estimate,  # ty:ignore[invalid-argument-type]
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
        case TaskType.mesh_lod_generation:
            count = 1
            service_subtype = ServiceSubtype.NEURON_MESH_SKELETONIZATION
        case TaskType.circuit_extraction:
            count = estimate_circuit_extraction_count(db_client=db_client, config_id=config_id)
            service_subtype = ServiceSubtype.CIRCUIT_EXTRACTION
        case (
            TaskType.circuit_simulation_neuron
            | TaskType.circuit_simulation_neurodamus_machine
            | TaskType.circuit_simulation_neurodamus_cluster
            | TaskType.circuit_simulation_inait_machine
        ):
            return _evaluate_circuit_simulation_parameters(
                db_client=db_client,
                simulation_id=config_id,
            )
        case TaskType.circuit_simulation_brian2_machine:
            return AccountingParameters(
                count=1,
                service_subtype=ServiceSubtype.BRIAN2_CIRCUIT_SIMULATION,
            )
        case TaskType.em_synapse_mapping:
            return AccountingParameters(
                count=1,
                service_subtype=ServiceSubtype.EM_SYNAPSE_MAPPING,
            )
        case TaskType.ion_channel_model_simulation_execution:
            count = 1
            service_subtype = ServiceSubtype.ION_CHANNEL_SIM
        case TaskType.single_neuron_simulation_execution:
            count = 1
            service_subtype = ServiceSubtype.SINGLE_CELL_SIM
        case TaskType.single_neuron_synaptome_simulation_execution:
            count = 1
            service_subtype = ServiceSubtype.SYNAPTOME_SIM
        case TaskType.morphology_skeletonization:
            count = estimate_skeletonization_count(db_client=db_client, config_id=config_id)
            service_subtype = ServiceSubtype.NEURON_MESH_SKELETONIZATION
        case _:
            # For other task types, use the default mapping
            count = 1
            service_subtype = ServiceSubtype.SMALL_SIM

    return AccountingParameters(
        count=count,
        service_subtype=service_subtype,
    )


_DURATION_BILLING_SCALES = {
    CircuitScale.microcircuit,
    CircuitScale.region,
    CircuitScale.system,
    CircuitScale.whole_brain,
}


def _evaluate_circuit_simulation_parameters(
    *,
    db_client: Client,
    simulation_id: UUID,
) -> AccountingParameters:
    simulation = db_client.get_entity(
        entity_id=simulation_id,
        entity_type=models.Simulation,
    )

    circuit = db_client.get_entity(entity_id=simulation.entity_id, entity_type=models.Circuit)

    try:
        service_subtype = CIRCUIT_SCALE_TO_SERVICE_SUBTYPE[circuit.scale]
    except KeyError as e:
        msg = f"Unsupported circuit scale '{circuit.scale}' for cost estimation"
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=msg) from e

    if circuit.scale in _DURATION_BILLING_SCALES:
        if simulation.number_neurons is None:
            msg = f"Simulation '{simulation.id}' has no number_neurons for cost estimation"
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=msg)
        duration_ms = _get_simulation_duration_ms(db_client=db_client, simulation=simulation)
        duration_s = duration_ms / 1000.0
        count = int(simulation.number_neurons * duration_s)
    else:
        count = 1

    return AccountingParameters(count=count, service_subtype=service_subtype)


def _get_simulation_duration_ms(
    *,
    db_client: Client,
    simulation: models.Simulation,
) -> float:
    """Get the simulation duration in milliseconds.

    Reads from the sonata_simulation_config asset (run.tstop), falling back to
    scan_parameters["initialize.simulation_length"], then to the default of 1000 ms.
    """
    default_duration_ms = 1000.0

    # Try reading from the SONATA simulation config asset
    try:
        config = select_json_asset_content(
            client=db_client,
            entity=simulation,
            selection={"label": AssetLabel.sonata_simulation_config},
        )
        tstop = config.get("run", {}).get("tstop")
        if tstop is not None:
            return float(tstop)
    except Exception:  # noqa: BLE001
        L.warning(f"Could not read sonata_simulation_config for simulation {simulation.id}")

    # Fallback to scan_parameters
    duration = simulation.scan_parameters.get("initialize.simulation_length")
    if duration is not None:
        return float(duration)

    return default_duration_ms


def generate_accounting_callbacks(
    task_type: TaskType,
    accounting_job_id: UUID,
    accounting_parameters: AccountingParameters,
    virtual_lab_id: UUID,
    project_id: UUID,
    callback_url: str,
) -> list[CallBack]:
    return [
        _generate_accounting_failure_callback(
            accounting_job_id=accounting_job_id,
        ),
        _generate_accounting_success_callback(
            task_type=task_type,
            accounting_job_id=accounting_job_id,
            count=accounting_parameters.count,
            accounting_service_subtype=accounting_parameters.service_subtype,
            project_id=project_id,
            virtual_lab_id=virtual_lab_id,
            callback_url=callback_url,
        ),
    ]


def _generate_accounting_failure_callback(
    accounting_job_id: UUID,
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
    task_type: TaskType,
    accounting_job_id: UUID,
    count: int,
    accounting_service_subtype: str,
    callback_url: str,
    virtual_lab_id: UUID,
    project_id: UUID,
) -> CallBack:
    """Builds the callback URL and payload for accounting success (usage addition).

    Points directly to the accounting service POST /usage/oneshot endpoint.
    """
    config = HttpRequestCallBackConfig(
        url=f"{callback_url}/success",
        method="POST",
        payload={
            "task_type": task_type,
            "job_id": str(accounting_job_id),
            "accounting_service_subtype": accounting_service_subtype,
            "count": count,
        },
        headers={
            "virtual-lab-id": str(virtual_lab_id),
            "project-id": str(project_id),
        },
    )
    return CallBack(
        event_type=CallBackEvent.job_on_success,
        action_type=CallBackAction.http_request_with_token,
        config=config,
    )


def finish_accounting_session(
    accounting_job_id: UUID,
    service_subtype: ServiceSubtype,
    count: int,
    project_id: UUID,
    http_client: httpx.Client,
) -> None:
    data = {
        "type": "oneshot",
        "subtype": service_subtype,
        "proj_id": str(project_id),
        "count": str(count),
        "job_id": str(accounting_job_id),
        "timestamp": get_current_timestamp(),
    }
    make_http_request(
        url=f"{settings.ACCOUNTING_BASE_URL}/usage/oneshot",
        method="POST",
        json=data,
        http_client=http_client,
    )
