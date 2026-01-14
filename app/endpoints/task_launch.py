import json
from datetime import UTC, datetime
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode

import entitysdk
import httpx
from entitysdk.models.execution import Execution
from entitysdk.types import ContentType, ExecutorType
from fastapi import APIRouter, Depends, Request

from app.config import settings
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

    CIRCUIT_EXTRACTION = entitysdk.models.CircuitExtractionConfig.__name__

    def get_execution_type(self) -> str:
        """Returns the execution activity type for this config type."""
        mapping = {
            TaskConfigType.CIRCUIT_EXTRACTION: entitysdk.models.CircuitExtractionExecution.__name__,
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
    activity_type: str,
    config_entity_type: TaskConfigType,
    config_entity_id: str,
) -> str:
    """Creates and registers an execution activity of the given type."""
    config_entity_type_resolved = getattr(entitysdk.models, config_entity_type)
    config_entity = db_client.get_entity(
        entity_type=config_entity_type_resolved, entity_id=config_entity_id
    )

    activity_type_resolved = getattr(entitysdk.models, activity_type)
    activity_model = activity_type_resolved(
        start_time=datetime.now(UTC),
        used=[config_entity],
        status="created",
        authorized_public=False,
    )
    execution_activity = db_client.register_entity(activity_model)
    L.info(f"Execution activity of type '{activity_type}' created (ID {execution_activity.id})")
    activity_id = str(execution_activity.id)
    return activity_id


def _update_execution_activity_executor(
    db_client: entitysdk.Client, activity_type: str, activity_id: str, job_id: str
) -> None:
    """Updates the execution activity by adding a job as executor."""
    activity_type_resolved = getattr(entitysdk.models, activity_type)
    exec_dict = {
        "executor": ExecutorType.single_node_job,
        "execution_id": job_id,
    }
    db_client.update_entity(
        entity_type=activity_type_resolved, entity_id=activity_id, attrs_or_entity=exec_dict
    )


def _update_execution_activity_status(
    db_client: entitysdk.Client, activity_type: str, activity_id: str, status: str
) -> None:
    """Updates the execution activity by setting a new status."""
    activity_type_resolved = getattr(entitysdk.models, activity_type)
    status_dict = {"status": status}
    db_client.update_entity(
        entity_type=activity_type_resolved, entity_id=activity_id, attrs_or_entity=status_dict
    )


def _check_activity_status(
    db_client: entitysdk.Client, activity_type: str, activity_id: str
) -> str:
    """Returns the current status of a given execution activity."""
    activity_type_resolved = getattr(entitysdk.models, activity_type)
    activity = db_client.get_entity(entity_type=activity_type_resolved, entity_id=activity_id)
    return activity.status


def _generate_failure_callback(request: Request, activity_id: str, activity_type: str) -> str:
    """Builds the callback URL for task failure notifications."""
    failure_endpoint_url = str(request.url_for("task_failure_endpoint"))
    query_params = urlencode({"activity_id": activity_id, "activity_type": activity_type})
    return f"{failure_endpoint_url}?{query_params}"


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
    activity_type = entity_type.get_execution_type()
    activity_id = _create_execution_activity(db_client, activity_type, entity_type, entity_id)
    _update_execution_activity_status(db_client, activity_type, activity_id, "pending")

    # Command line arguments
    entity_cache = True
    output_root = "./grid_scan"  # TODO: Check root
    cmd_args = [
        f"--entity_type {entity_type}",
        f"--entity_id {entity_id}",
        f"--config_asset_id {config_asset_id}",
        f"--entity_cache {entity_cache}",
        f"--scan_output_root {output_root}",
        f"--virtual_lab_id {virtual_lab_id}",
        f"--project_id {project_id}",
        f"--activity_type {activity_type}",
        f"--activity_id {activity_id}",
    ]

    # Job specification
    time_limit = (
        "00:10"  # TODO: Determine and set proper time limit and compute/memory requirements
    )
    release_tag = settings.APP_VERSION.split("-")[0]
    # TODO: Use failure_callback_url in job_data for launch system to call back on task failure
    _failure_callback_url = _generate_failure_callback(request, activity_id, activity_type)
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
        _update_execution_activity_status(db_client, activity_type, activity_id, "error")
        msg = f"Job submission failed!\n{json.loads(response.text)}"
        raise RuntimeError(msg)
    response_body = response.json()
    job_id = response_body["id"]
    L.info(f"Job submitted (ID {job_id})")

    # Add job as executor to activity
    _update_execution_activity_executor(db_client, activity_type, activity_id, job_id)

    return activity_id, activity_type, job_id


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
    activity_id = None

    # Determine config asset
    config_asset_id = _get_config_asset(db_client, entity_type, entity_id)

    # Launch task
    activity_id, _activity_type, _job_id = _submit_task_job(
        db_client, ls_client, entity_type, entity_id, config_asset_id, request
    )

    return activity_id


@router.post(
    "/task-failure",
    summary="Task failure callback",
    description=(
        "Callback endpoint to mark a task execution activity as failed. "
        "Used by the launch-system to report task failures."
    ),
)
def task_failure_endpoint(
    activity_id: str,
    activity_type: str,
    db_client: Annotated[entitysdk.Client, Depends(get_db_client)],
) -> dict:
    if _check_activity_status(db_client, activity_type, activity_id) != "done":
        # Set the execution activity status to "error"
        _update_execution_activity_status(db_client, activity_type, activity_id, "error")

    return
