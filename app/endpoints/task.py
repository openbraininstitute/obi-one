from http import HTTPStatus
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.config import settings
from app.dependencies.accounting import AccountingSessionFactoryDep
from app.dependencies.auth import UserContextWithProjectIdDep, user_verified
from app.dependencies.callback import CallBackUrlDep
from app.dependencies.compute_cell import ComputeCellDep
from app.dependencies.entitysdk import DatabaseClientDep
from app.dependencies.launch_system import LaunchSystemClientDep
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from app.mappings import TASK_DEFINITIONS
from app.schemas.task import (
    TaskAccountingCreate,
    TaskAccountingInfo,
    TaskCallBackSuccessRequest,
    TaskLaunchInfo,
    TaskLaunchSubmit,
)
from app.services import accounting as accounting_service, task as task_service
from app.types import TaskType

from obi_one.scientific.library.circuit_metrics import CircuitStatsLevelOfDetail, get_circuit_metrics


router = APIRouter(
    prefix="/declared/task",
    tags=["declared"],
    dependencies=[Depends(user_verified)],
)

import json
import numpy as np
from app.schemas.task import TaskDefinition
from app.utils import db_sdk
from obi_one import deserialize_obi_object_from_json_data
DISK_SPACE_LIMIT_GB = 20

def get_required_cpu_memory_combo(mem_gb_required: float) -> (int, int):
    # From launch-system
    CPU_MEMORY_COMBINATIONS: dict[int, set[int]] = {
        1: {2, 4, 6, 8},
        2: {4, 8, 12, 16},
        4: {8, 16, 24, 30},
        8: {16, 32, 48, 60},
        16: {32, 64, 96, 120},
    }
    for ncpu, mem_values in CPU_MEMORY_COMBINATIONS.items():
        for mem in sorted(mem_values):
            if mem > mem_gb_required:
                return (ncpu, mem)
    msg = "No CPU/memory combination found!"
    raise ValueError(msg)

def update_resources(json_model: TaskLaunchSubmit, db_client: DatabaseClientDep, task_definition: TaskDefinition) -> None:
    """Updates the machine resources in the task definition (in-place)."""
    match task_definition.task_type:
        case TaskType.circuit_extraction:
            # Get extraction config
            config = db_client.get_entity(
                entity_id=json_model.config_id,
                entity_type=task_definition.config_type,
            )
            config_asset_id = db_sdk.get_config_asset(
                client=db_client,
                config=config,
                asset_label=task_definition.config_asset_label,
            ).id

            json_str = db_client.download_content(
                entity_id=json_model.config_id,
                entity_type=task_definition.config_type,
                asset_id=config_asset_id
            ).decode(encoding="utf-8")

            json_dict = json.loads(json_str)
            single_config = deserialize_obi_object_from_json_data(json_dict)

            # Get parent circuit metrics
            level_of_detail_nodes_dict = {"_ALL_": CircuitStatsLevelOfDetail.basic}
            level_of_detail_edges_dict = {"_ALL_": CircuitStatsLevelOfDetail.basic}
            circuit_metrics = get_circuit_metrics(
                circuit_id=config.circuit_id,
                db_client=db_client,
                level_of_detail_nodes=level_of_detail_nodes_dict,
                level_of_detail_edges=level_of_detail_edges_dict,
            )

            # Get output circuit size
            # TODO: Requires resolving the neuron set based in the circuit
            # > output_size_neurons = len(single_config.neuron_set.get_neuron_ids(circuit))
            output_size_neurons = 0  # Disable for now

            # Estimate memory based on number of input neurons
            nbio = np.sum([npop.number_of_nodes for npop in circuit_metrics.biophysical_node_populations])
            nvirt = np.sum([npop.number_of_nodes for npop in circuit_metrics.virtual_node_populations])
            if single_config.initialize.do_virtual:
                input_size_neurons = nbio + nvirt
            else:
                input_size_neurons = nbio

            mem_gb_required = 1 + 55e-6 * input_size_neurons
            ncpu, mem_gb = get_required_cpu_memory_combo(mem_gb_required)

            # Estimate time limit
            time_h = np.ceil(input_size_neurons * 5e-6)

            # Estimate disk space
            sbio = np.sum([epop.number_of_edges for epop in circuit_metrics.chemical_edge_populations if epop.source_name in circuit_metrics.names_of_biophys_node_populations])
            svirt = np.sum([epop.number_of_edges for epop in circuit_metrics.chemical_edge_populations if epop.source_name in circuit_metrics.names_of_virtual_node_populations])
            if single_config.initialize.do_virtual:
                input_size_synapses = sbio + svirt
            else:
                input_size_synapses = sbio
            output_size_synapses = (output_size_neurons / nbio) * input_size_synapses
            output_size_gb = output_size_synapses * 2e-7
            if outout_size_gb + DISK_SPACE_LIMIT_GB:
                msg = "Not enough disk space!"
                raise ValueError(msg)

            # Update resources
            task_definition.resources=MachineResources(
                cores=ncpu,
                memory=mem_gb,
                timelimit=f"{time_h:02d}:00",
                compute_cell=task_definition.resources.compute_cell,
            )
        case _:
            # Nothing to update
            pass


@router.post(
    "/launch",
    summary="Launch a task.",
    description=(
        "Launches an obi-one task as a dedicated job on the launch-system. "
        "The type of task is determined based on the config entity provided."
    ),
)
def task_launch_endpoint(
    json_model: TaskLaunchSubmit,
    db_client: DatabaseClientDep,
    ls_client: LaunchSystemClientDep,
    callback_url: CallBackUrlDep,
    user_context: UserContextWithProjectIdDep,
    compute_cell: ComputeCellDep,
    accounting_factory: AccountingSessionFactoryDep,
) -> TaskLaunchInfo:
    project_context = db_client.project_context
    task_definition = TASK_DEFINITIONS[json_model.task_type]

    accounting_info = accounting_service.estimate_task_cost(
        db_client=db_client,
        config_id=json_model.config_id,
        project_context=project_context,
        task_definition=task_definition,
        accounting_factory=accounting_factory,
    )
    accounting_session = accounting_service.make_task_reservation(
        user_context=user_context,
        accounting_factory=accounting_factory,
        accounting_parameters=accounting_info.parameters,
    )
    accounting_callbacks = accounting_service.generate_accounting_callbacks(
        task_type=json_model.task_type,
        accounting_job_id=accounting_session._job_id,  # noqa: SLF001
        count=accounting_info.parameters.count,
        project_id=user_context.project_id,
        virtual_lab_id=user_context.virtual_lab_id,
        callback_url=callback_url,
    )
    try:
        update_resources(
            json_model=json_model,
            db_client=db_client,
            task_definition=task_definition
        )
        # TODO: Check if resource update has to be done before calling the accounting service!

        return task_service.submit_task_job(
            db_client=db_client,
            ls_client=ls_client,
            callback_url=callback_url,
            compute_cell=compute_cell,
            config_id=json_model.config_id,
            project_context=project_context,
            task_definition=task_definition,
            callbacks=accounting_callbacks,
        )
    except Exception as exc:
        # TODO: Remove once
        # https://github.com/openbraininstitute/accounting-sdk/issues/29 is addressed
        if settings.ACCOUNTING_DISABLED:
            accounting_session.finish()
        else:
            accounting_session.finish(exc_type=type(exc))
        L.exception("Failed to submit task job")
        raise ApiError(
            message="Failed to submit task job",
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=ApiErrorCode.INTERNAL_ERROR,
        ) from exc


@router.post(
    "/estimate",
    summary="Estimate task cost.",
    description=(
        "Estimates the cost in credits for launching an obi-one task. "
        "Takes the same parameters as /launch and returns a cost estimate."
    ),
)
def estimate_endpoint(
    json_model: TaskAccountingCreate,
    db_client: DatabaseClientDep,
    _user_context: UserContextWithProjectIdDep,  # ensure there is a project_id
    accounting_factory: AccountingSessionFactoryDep,
) -> TaskAccountingInfo:
    """Estimates the cost for launching a task."""
    return accounting_service.estimate_task_cost(
        db_client=db_client,
        config_id=json_model.config_id,
        project_context=db_client.project_context,
        accounting_factory=accounting_factory,
        task_definition=TASK_DEFINITIONS[json_model.task_type],
    )


@router.post(
    "/callback/failure",
    summary="Task failure callback",
    description=(
        "Callback endpoint to mark a task execution activity as failed. "
        "Used by the launch-system to report task failures."
    ),
)
def task_failure_endpoint(
    task_type: TaskType,
    activity_id: UUID,
    db_client: DatabaseClientDep,
    _user_context: UserContextWithProjectIdDep,
) -> None:
    task_service.handle_task_failure_callback(
        db_client=db_client,
        activity_id=activity_id,
        task_definition=TASK_DEFINITIONS[task_type],
    )
    return Response(status_code=HTTPStatus.NO_CONTENT)


@router.post(
    "/callback/success",
    summary="Task success callback",
    description=("Callback endpoint that is called on task success."),
)
def task_success_endpoint(
    json_model: TaskCallBackSuccessRequest,
    accounting_factory: AccountingSessionFactoryDep,
    user_context: UserContextWithProjectIdDep,
) -> None:
    task_definition = TASK_DEFINITIONS[json_model.task_type]
    accounting_service.finish_accounting_session(
        accounting_job_id=json_model.job_id,
        service_subtype=task_definition.accounting_service_subtype,
        count=json_model.count,
        project_id=user_context.project_id,
        http_client=accounting_factory._http_client,  # noqa: SLF001
    )
    return Response(status_code=HTTPStatus.NO_CONTENT)
