import json
from datetime import UTC, datetime
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

import entitysdk
import httpx
from entitysdk.types import CircuitScale, ContentType, ExecutorType
from fastapi import APIRouter, Depends, HTTPException, Request
from obp_accounting_sdk._async.factory import AsyncAccountingSessionFactory
from obp_accounting_sdk.constants import ServiceSubtype

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


class TaskConfigType(StrEnum):
    """List of entitycore config types supported for job submission."""

    CIRCUIT_EXTRACTION_CONFIG = entitysdk.models.CircuitExtractionConfig.__name__
    SIMULATION = entitysdk.models.Simulation.__name__

    def get_execution_type(self) -> str:
        """Returns the execution activity type for this config type."""
        mapping = {
            TaskConfigType.CIRCUIT_EXTRACTION_CONFIG: (
                entitysdk.models.CircuitExtractionExecution.__name__
            ),
            TaskConfigType.SIMULATION: entitysdk.models.SimulationExecution.__name__,
        }
        return mapping[self]

    def get_service_subtype(self) -> ServiceSubtype:
        """Returns the accounting service subtype for this config type."""
        mapping = {
            TaskConfigType.CIRCUIT_EXTRACTION_CONFIG: ServiceSubtype.SMALL_CIRCUIT_SIM,
        }
        return mapping[self]


def _get_config_asset(
    db_client: entitysdk.Client, entity_type: TaskConfigType, entity_id: str
) -> str:
    """Determines the asset ID of the JSON config asset."""
    entity_type_resolved = getattr(entitysdk.models, entity_type)
    entity = db_client.get_entity(entity_id=entity_id, entity_type=entity_type_resolved)
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
    execution_activity_type: str,
    config_entity_type: TaskConfigType,
    config_entity_id: str,
) -> str:
    """Creates and registers an execution activity of the given type."""
    config_entity_type_resolved = getattr(entitysdk.models, config_entity_type)
    config_entity = db_client.get_entity(
        entity_type=config_entity_type_resolved, entity_id=config_entity_id
    )

    execution_activity_type_resolved = getattr(entitysdk.models, execution_activity_type)
    activity_model = execution_activity_type_resolved(
        start_time=datetime.now(UTC),
        used=[config_entity],
        status="created",
        authorized_public=False,
    )
    execution_activity = db_client.register_entity(activity_model)
    L.info(
        f"Execution activity of type '{execution_activity_type}' created "
        f"(ID {execution_activity.id})"
    )
    execution_activity_id = str(execution_activity.id)
    return execution_activity_id


def _update_execution_activity_executor(
    db_client: entitysdk.Client,
    execution_activity_type: str,
    execution_activity_id: str,
    job_id: str,
) -> None:
    """Updates the execution activity by adding a job as executor."""
    execution_activity_type_resolved = getattr(entitysdk.models, execution_activity_type)
    exec_dict = {
        "executor": ExecutorType.single_node_job,
        "execution_id": job_id,
    }
    db_client.update_entity(
        entity_type=execution_activity_type_resolved,
        entity_id=execution_activity_id,
        attrs_or_entity=exec_dict,
    )


def _update_execution_activity_status(
    db_client: entitysdk.Client,
    execution_activity_type: str,
    execution_activity_id: str,
    status: str,
) -> None:
    """Updates the execution activity by setting a new status."""
    execution_activity_type_resolved = getattr(entitysdk.models, execution_activity_type)
    status_dict = {"status": status}
    db_client.update_entity(
        entity_type=execution_activity_type_resolved,
        entity_id=execution_activity_id,
        attrs_or_entity=status_dict,
    )


def _check_execution_activity_status(
    db_client: entitysdk.Client, execution_activity_type: str, execution_activity_id: str
) -> str:
    """Returns the current status of a given execution activity."""
    execution_activity_type_resolved = getattr(entitysdk.models, execution_activity_type)
    execution_activity = db_client.get_entity(
        entity_type=execution_activity_type_resolved, entity_id=execution_activity_id
    )
    return execution_activity.status


def _generate_failure_callback(
    request: Request, execution_activity_id: str, execution_activity_type: str
) -> str:
    """Builds the callback URL for task failure notifications."""
    failure_endpoint_url = str(request.url_for("task_failure_endpoint"))
    query_params = urlencode(
        {
            "execution_activity_id": execution_activity_id,
            "execution_activity_type": execution_activity_type,
        }
    )
    return f"{failure_endpoint_url}?{query_params}"


def _evaluate_accounting_parameters(
    db_client: entitysdk.Client,
    entity_type: TaskConfigType,
    entity_id: str,
) -> dict:
    """Evaluates accounting parameters from the task configuration.

    Returns the service subtype and count needed for cost estimation.
    For Simulation configs, determines the service subtype based on the circuit scale
    and uses the neuron_count from the simulation entity for the count.
    """
    if entity_type == TaskConfigType.SIMULATION:
        # Get the Simulation entity
        simulation_entity = db_client.get_entity(
            entity_id=entity_id, entity_type=entitysdk.models.Simulation
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
        # For other config types, use the default mapping
        count = 1  # Single job
        service_subtype = entity_type.get_service_subtype()

    return {
        "service_subtype": service_subtype,
        "count": count,
    }


def _submit_task_job(
    db_client: entitysdk.Client,
    ls_client: httpx.Client,
    entity_type: TaskConfigType,
    entity_id: str,
    config_asset_id: str,
    request: Request,
) -> str | None:
    """Creates an activity and submits a task as a job on the launch-system."""
    if not db_client.project_context:
        msg = "Project context is required!"
        raise ValueError(msg)
    project_id = str(db_client.project_context.project_id)
    virtual_lab_id = str(db_client.project_context.virtual_lab_id)

    # Create activity and set to pending for launching the job
    execution_activity_type = entity_type.get_execution_type()
    execution_activity_id = _create_execution_activity(
        db_client, execution_activity_type, entity_type, entity_id
    )
    _update_execution_activity_status(
        db_client, execution_activity_type, execution_activity_id, "pending"
    )

    # Command line arguments
    entity_cache = True
    output_root = settings.LAUNCH_SYSTEM_OUTPUT_DIR
    cmd_args = [
        f"--entity_type {entity_type}",
        f"--entity_id {entity_id}",
        f"--config_asset_id {config_asset_id}",
        f"--entity_cache {entity_cache}",
        f"--scan_output_root {output_root}",
        f"--virtual_lab_id {virtual_lab_id}",
        f"--project_id {project_id}",
        f"--execution_activity_type {execution_activity_type}",
        f"--execution_activity_id {execution_activity_id}",
    ]

    # Job specification
    time_limit = (
        "00:10"  # TODO: Determine and set proper time limit and compute/memory requirements
    )
    release_tag = settings.APP_VERSION.split("-")[0]
    # TODO: Use failure_callback_url in job_data for launch system to call back on task failure
    _failure_callback_url = _generate_failure_callback(
        request, execution_activity_id, execution_activity_type
    )
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
    }

    # Submit job
    response = ls_client.post(url="/job", json=job_data)
    if response.status_code != HTTPStatus.OK:
        _update_execution_activity_status(
            db_client, execution_activity_type, execution_activity_id, "error"
        )
        msg = f"Job submission failed!\n{json.loads(response.text)}"
        raise RuntimeError(msg)
    response_body = response.json()
    job_id = response_body["id"]
    L.info(f"Job submitted (ID {job_id})")

    # Add job as executor to activity
    _update_execution_activity_executor(
        db_client, execution_activity_type, execution_activity_id, job_id
    )

    return execution_activity_id, execution_activity_type, job_id


@router.post(
    "/task-launch",
    summary="Task launch",
    description=(
        "Launches an obi-one task as a dedicated job on the launch-system. "
        "The type of task is determined based on the config entity provided."
    ),
)
def task_launch_endpoint(
    request: Request,
    entity_type: TaskConfigType,
    entity_id: str,
    db_client: Annotated[entitysdk.Client, Depends(get_db_client)],
    ls_client: Annotated[httpx.Client, Depends(get_ls_client)],
) -> str | None:
    execution_activity_id = None

    # Determine config asset
    config_asset_id = _get_config_asset(db_client, entity_type, entity_id)

    # Launch task
    execution_activity_id, _execution_activity_type, _job_id = _submit_task_job(
        db_client, ls_client, entity_type, entity_id, config_asset_id, request
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
    entity_type: TaskConfigType,
    entity_id: str,
    db_client: Annotated[entitysdk.Client, Depends(get_db_client)],
    AsyncAccountingSessionFactoryDep: Annotated[  # noqa: N803
        AsyncAccountingSessionFactory, Depends(get_accounting_factory)
    ],
) -> dict:
    """Estimates the cost for a task launch."""
    # Evaluate accounting parameters
    accounting_parameters = _evaluate_accounting_parameters(
        db_client, entity_type, entity_id
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
    current_status = _check_execution_activity_status(
        db_client, execution_activity_type, execution_activity_id
    )
    if current_status != "done":
        # Set the execution activity status to "error"
        _update_execution_activity_status(
            db_client, execution_activity_type, execution_activity_id, "error"
        )
