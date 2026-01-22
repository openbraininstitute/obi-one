import json
from datetime import UTC, datetime
from enum import StrEnum, auto
from http import HTTPStatus
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode
from uuid import UUID

import entitysdk
import httpx
from entitysdk.types import CircuitScale, ContentType, ExecutorType
from fastapi import APIRouter, Depends, HTTPException, Request
from obp_accounting_sdk._async.factory import AsyncAccountingSessionFactory
from obp_accounting_sdk.constants import ServiceSubtype
from pydantic import BaseModel

from app.config import settings
from app.dependencies.accounting import get_accounting_factory
from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client as get_db_client
from app.dependencies.launchsystem import get_client as get_ls_client
from app.logger import L

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])

"""Path to the obi-one repository"""
OBI_ONE_REPO = "https://github.com/openbraininstitute/obi-one.git"

"""Path to launch script within the repository. Must contain code.py and requirements.txt."""
OBI_ONE_LAUNCH_PATH = "launch_scripts/launch_task_for_single_config_asset"


class TaskType(StrEnum):
    """Task types supported for job submission."""

    circuit_extraction = auto()
    circuit_simulation = auto()


class TaskDefinition(BaseModel):
    """Definition of a task type with its associated models and configuration."""

    config_cls: type[entitysdk.models.Entity]
    execution_cls: type[Any]  # Execution activity class (e.g., SimulationExecution)
    accounting_service_subtype: ServiceSubtype


# Mapping of task types to their definitions
TASK_DEFINITIONS: dict[TaskType, TaskDefinition] = {
    TaskType.circuit_extraction: TaskDefinition(
        config_cls=entitysdk.models.CircuitExtractionConfig,
        execution_cls=entitysdk.models.CircuitExtractionExecution,
        accounting_service_subtype=ServiceSubtype.SMALL_CIRCUIT_SIM,
    ),
    TaskType.circuit_simulation: TaskDefinition(
        config_cls=entitysdk.models.Simulation,
        execution_cls=entitysdk.models.SimulationExecution,
        accounting_service_subtype=ServiceSubtype.SMALL_SIM,  # May be overridden by circuit scale
    ),
}


class TaskLaunchCreate(BaseModel):
    """Request model for task launch."""

    task_type: TaskType
    config_id: UUID


class TaskEstimateCreate(BaseModel):
    """Request model for task cost estimate."""

    task_type: TaskType
    config_id: UUID


def _get_config_asset(
    db_client: entitysdk.Client, task_type: TaskType, entity_id: str
) -> str:
    """Determines the asset ID of the JSON config asset."""
    task_def = TASK_DEFINITIONS[task_type]
    entity = db_client.get_entity(entity_id=entity_id, entity_type=task_def.config_cls)
    config_assets = [
        _asset
        for _asset in entity.assets
        if "_config" in _asset.label and _asset.content_type == ContentType.application_json
    ]
    if len(config_assets) != 1:
        msg = (
            f"Config asset for entity '{entity.id}' could not be determined "
            f"({len(config_assets)} found)!"
        )
        raise ValueError(msg)
    config_asset_id = str(config_assets[0].id)
    return config_asset_id


def _create_execution_activity(
    db_client: entitysdk.Client,
    task_type: TaskType,
    config_entity_id: str,
) -> str:
    """Creates and registers an execution activity of the given type."""
    task_def = TASK_DEFINITIONS[task_type]
    config_entity = db_client.get_entity(
        entity_type=task_def.config_cls, entity_id=config_entity_id
    )

    activity_model = task_def.execution_cls(
        start_time=datetime.now(UTC),
        used=[config_entity],
        status="created",
        authorized_public=False,
    )
    execution_activity = db_client.register_entity(activity_model)
    L.info(
        f"Execution activity of type '{task_def.execution_cls.__name__}' created "
        f"(ID {execution_activity.id})"
    )
    execution_activity_id = str(execution_activity.id)
    return execution_activity_id


def _update_execution_activity_executor(
    db_client: entitysdk.Client,
    task_type: TaskType,
    execution_activity_id: str,
    job_id: str,
) -> None:
    """Updates the execution activity by adding a job as executor."""
    task_def = TASK_DEFINITIONS[task_type]
    exec_dict = {
        "executor": ExecutorType.single_node_job,
        "execution_id": job_id,
    }
    db_client.update_entity(
        entity_type=task_def.execution_cls,
        entity_id=execution_activity_id,
        attrs_or_entity=exec_dict,
    )


def _update_execution_activity_status(
    db_client: entitysdk.Client,
    task_type: TaskType,
    execution_activity_id: str,
    status: str,
) -> None:
    """Updates the execution activity by setting a new status."""
    task_def = TASK_DEFINITIONS[task_type]
    status_dict = {"status": status}
    db_client.update_entity(
        entity_type=task_def.execution_cls,
        entity_id=execution_activity_id,
        attrs_or_entity=status_dict,
    )


def _check_execution_activity_status(
    db_client: entitysdk.Client, task_type: TaskType, execution_activity_id: str
) -> str:
    """Returns the current status of a given execution activity."""
    task_def = TASK_DEFINITIONS[task_type]
    execution_activity = db_client.get_entity(
        entity_type=task_def.execution_cls, entity_id=execution_activity_id
    )
    return execution_activity.status


def _generate_failure_callback(
    request: Request, execution_activity_id: str, task_type: TaskType
) -> str:
    """Builds the callback URL for task failure notifications."""
    failure_endpoint_url = str(request.url_for("task_failure_endpoint"))
    task_def = TASK_DEFINITIONS[task_type]
    query_params = urlencode(
        {
            "execution_activity_id": execution_activity_id,
            "execution_activity_type": task_def.execution_cls.__name__,
        }
    )
    return f"{failure_endpoint_url}?{query_params}"


def _generate_accounting_failure_callback(
    accounting_job_id: str,
) -> str:
    """Builds the callback URL for accounting failure (reservation deletion).

    Points directly to the accounting service DELETE endpoint.
    The job_id is included in the URL path.
    """
    callback_url = f"{settings.ACCOUNTING_BASE_URL}/reservation/oneshot/{accounting_job_id}"
    return callback_url


def _generate_accounting_success_callback(
    accounting_job_id: str,
    service_subtype: ServiceSubtype,
    count: int,
    project_id: str,
) -> tuple[str, dict]:
    """Builds the callback URL and payload for accounting success (usage addition).

    Points directly to the accounting service POST /usage/oneshot endpoint.
    """
    callback_url = f"{settings.ACCOUNTING_BASE_URL}/usage/oneshot"
    # Format timestamp as ISO 8601 with Z suffix
    timestamp = datetime.now(UTC).isoformat()
    payload = {
        "type": "oneshot",
        "subtype": service_subtype,
        "proj_id": project_id,
        "job_id": accounting_job_id,
        "count": count,
        "timestamp": timestamp,
    }
    return callback_url, payload


def _evaluate_accounting_parameters(
    db_client: entitysdk.Client,
    task_type: TaskType,
    entity_id: str,
) -> dict:
    """Evaluates accounting parameters from the task configuration.

    Returns the service subtype and count needed for cost estimation.
    For Simulation configs, determines the service subtype based on the circuit scale
    and uses the neuron_count from the simulation entity for the count.
    """
    if task_type == TaskType.circuit_simulation:
        # Get the Simulation entity
        task_def = TASK_DEFINITIONS[task_type]
        simulation_entity = db_client.get_entity(
            entity_id=entity_id, entity_type=task_def.config_cls
        )
        # Use neuron_count from the simulation entity
        # TODO: actually use the circuit and simulation files to determine the count
        count = simulation_entity.neuron_count
        # Get the circuit ID from the simulation's entity_id field
        circuit_id = str(simulation_entity.entity_id)
        # Get the Circuit entity
        circuit_entity = db_client.get_entity(
            entity_id=circuit_id, entity_type=entitysdk.models.Circuit
        )
        # Get the scale and map it to service subtype
        circuit_scale = circuit_entity.scale
        scale_to_subtype = {
            CircuitScale.small: ServiceSubtype.SMALL_SIM,
            CircuitScale.microcircuit: ServiceSubtype.MICROCIRCUIT_SIM,
            CircuitScale.region: ServiceSubtype.REGION_SIM,
            CircuitScale.system: ServiceSubtype.SYSTEM_SIM,
            CircuitScale.whole_brain: ServiceSubtype.WHOLE_BRAIN_SIM,
        }
        service_subtype = scale_to_subtype.get(circuit_scale)
        if service_subtype is None:
            msg = f"Unsupported circuit scale '{circuit_scale}' for cost estimation"
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=msg)
    else:
        # For other task types, use the default mapping
        count = 1  # Single job
        task_def = TASK_DEFINITIONS[task_type]
        service_subtype = task_def.accounting_service_subtype

    return {
        "service_subtype": service_subtype,
        "count": count,
    }


def _submit_task_job(
    db_client: entitysdk.Client,
    ls_client: httpx.Client,
    task_type: TaskType,
    entity_id: str,
    config_asset_id: str,
    request: Request,
    accounting_job_id: str,
    service_subtype: ServiceSubtype,
    count: int,
    project_id: str,
) -> tuple[str, TaskType, str]:
    """Creates an activity and submits a task as a job on the launch-system."""
    if not db_client.project_context:
        msg = "Project context is required!"
        raise ValueError(msg)
    project_id = str(db_client.project_context.project_id)
    virtual_lab_id = str(db_client.project_context.virtual_lab_id)

    task_def = TASK_DEFINITIONS[task_type]

    # Create activity and set to pending for launching the job
    execution_activity_id = _create_execution_activity(
        db_client, task_type, entity_id
    )
    _update_execution_activity_status(
        db_client, task_type, execution_activity_id, "pending"
    )

    # Command line arguments
    entity_cache = True
    output_root = settings.LAUNCH_SYSTEM_OUTPUT_DIR
    cmd_args = [
        f"--entity_type {task_def.config_cls.__name__}",
        f"--entity_id {entity_id}",
        f"--config_asset_id {config_asset_id}",
        f"--entity_cache {entity_cache}",
        f"--scan_output_root {output_root}",
        f"--virtual_lab_id {virtual_lab_id}",
        f"--project_id {project_id}",
        f"--execution_activity_type {task_def.execution_cls.__name__}",
        f"--execution_activity_id {execution_activity_id}",
    ]

    # Job specification
    time_limit = (
        "00:10"  # TODO: Determine and set proper time limit and compute/memory requirements
    )
    release_tag = settings.APP_VERSION.split("-")[0]
    # TODO: Use failure_callback_url in job_data for launch system to call back on task failure
    _failure_callback_url = _generate_failure_callback(
        request, execution_activity_id, task_type
    )

    # Generate accounting callbacks (pointing directly to accounting service)
    accounting_failure_callback_url = _generate_accounting_failure_callback(
        accounting_job_id
    )
    (
        accounting_success_callback_url,
        accounting_success_payload,
    ) = _generate_accounting_success_callback(
        accounting_job_id, service_subtype, count, project_id
    )

    # Format callbacks for launch system
    callbacks = [
        {
            "action_type": "http_request_with_token",
            "event_type": "job_on_failure",
            "config": {
                "url": accounting_failure_callback_url,
                "method": "DELETE",
            },
        },
        {
            "action_type": "http_request_with_token",
            "event_type": "job_on_success",
            "config": {
                "url": accounting_success_callback_url,
                "method": "POST",
                "payload": accounting_success_payload,
            },
        },
    ]

    job_data = {
        "resources": {"cores": 1, "memory": 2, "timelimit": time_limit},
        "code": {
            "type": "python_repository",
            "location": OBI_ONE_REPO,
            "ref": f"tag:{release_tag}",
            "path": str(Path(OBI_ONE_LAUNCH_PATH) / "code.py"),
            "dependencies": str(Path(OBI_ONE_LAUNCH_PATH) / "requirements.txt"),
        },
        "inputs": cmd_args,
        "project_id": project_id,
        "callbacks": callbacks,
    }

    # Submit job
    response = ls_client.post(url="/job", json=job_data)
    if response.status_code != HTTPStatus.OK:
        _update_execution_activity_status(
            db_client, task_type, execution_activity_id, "error"
        )
        msg = f"Job submission failed!\n{json.loads(response.text)}"
        raise RuntimeError(msg)
    response_body = response.json()
    job_id = response_body["id"]
    L.info(f"Job submitted (ID {job_id})")

    # Add job as executor to activity
    _update_execution_activity_executor(
        db_client, task_type, execution_activity_id, job_id
    )

    return execution_activity_id, task_type, job_id


@router.post(
    "/task-launch",
    summary="Task launch",
    description=(
        "Launches an obi-one task as a dedicated job on the launch-system. "
        "The type of task is determined based on the config entity provided."
    ),
)
async def task_launch_endpoint(
    request: Request,
    json_model: TaskLaunchCreate,
    db_client: Annotated[entitysdk.Client, Depends(get_db_client)],
    ls_client: Annotated[httpx.Client, Depends(get_ls_client)],
    AsyncAccountingSessionFactoryDep: Annotated[  # noqa: N803
        AsyncAccountingSessionFactory, Depends(get_accounting_factory)
    ],
) -> str | None:

    config_asset_id = _get_config_asset(
        db_client, json_model.task_type, str(json_model.config_id)
    )

    # Step 1: Evaluate accounting parameters
    accounting_parameters = _evaluate_accounting_parameters(
        db_client, json_model.task_type, str(json_model.config_id)
    )
    service_subtype = accounting_parameters["service_subtype"]
    count = accounting_parameters["count"]

    if not db_client.project_context:
        msg = "Project context is required!"
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=msg)

    # Step 2: Reserve
    project_id = str(db_client.project_context.project_id)
    virtual_lab_id = str(db_client.project_context.virtual_lab_id)

    reservation_result = await AsyncAccountingSessionFactoryDep.reserve_oneshot(
        subtype=service_subtype,
        count=count,
        proj_id=project_id,
        vlab_id=virtual_lab_id,
    )
    accounting_job_id = str(reservation_result.job_id)
    L.info(
        f"Accounting parameters reserved: subtype={service_subtype}, "
        f"count={count}, job_id={accounting_job_id}"
    )

    # Step 3: Create activity and submit task job
    execution_activity_id, _task_type, _job_id = _submit_task_job(
        db_client,
        ls_client,
        json_model.task_type,
        str(json_model.config_id),
        config_asset_id,
        request,
        accounting_job_id,
        service_subtype,
        count,
        project_id,
    )

    return execution_activity_id


@router.post(
    "/estimate",
    summary="Task cost estimate",
    description=(
        "Estimates the cost in credits for launching an obi-one task. "
        "Takes the same parameters as /task-launch and returns a cost estimate."
    ),
)
async def estimate_endpoint(
    json_model: TaskEstimateCreate,
    db_client: Annotated[entitysdk.Client, Depends(get_db_client)],
    AsyncAccountingSessionFactoryDep: Annotated[  # noqa: N803
        AsyncAccountingSessionFactory, Depends(get_accounting_factory)
    ],
) -> dict:
    """Estimates the cost for a task launch."""
    # Evaluate accounting parameters
    accounting_parameters = _evaluate_accounting_parameters(
        db_client, json_model.task_type, str(json_model.config_id)
    )
    service_subtype = accounting_parameters["service_subtype"]
    count = accounting_parameters["count"]

    # Get project context for proj_id and vlab_id
    if not db_client.project_context:
        msg = "Project context is required!"
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=msg)
    project_id = str(db_client.project_context.project_id)
    virtual_lab_id = str(db_client.project_context.virtual_lab_id)

    # Compute cost estimate using accounting SDK
    cost_estimate = await AsyncAccountingSessionFactoryDep.estimate_oneshot_cost(
        subtype=service_subtype,
        count=count,
        proj_id=project_id,
        vlab_id=virtual_lab_id,
    )

    return {
        "cost": str(cost_estimate),
        "accounting_parameters": accounting_parameters,
    }


@router.post(
    "/task-failure",
    summary="Task failure callback",
    description=(
        "Callback endpoint to mark a task execution activity as failed. "
        "Used by the launch-system to report task failures."
    ),
)
def task_failure_endpoint(
    execution_activity_id: str,
    execution_activity_type: str,
    db_client: Annotated[entitysdk.Client, Depends(get_db_client)],
) -> None:
    # Map execution activity type name to TaskType
    execution_type_to_task_type = {
        entitysdk.models.CircuitExtractionExecution.__name__: TaskType.circuit_extraction,
        entitysdk.models.SimulationExecution.__name__: TaskType.circuit_simulation,
    }
    task_type = execution_type_to_task_type.get(execution_activity_type)
    if task_type is None:
        msg = f"Unknown execution activity type: {execution_activity_type}"
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=msg)

    current_status = _check_execution_activity_status(
        db_client, task_type, execution_activity_id
    )
    if current_status != "done":
        # Set the execution activity status to "error"
        _update_execution_activity_status(
            db_client, task_type, execution_activity_id, "error"
        )
