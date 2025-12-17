import json
from datetime import UTC, datetime
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path
from typing import Annotated

import entitysdk
import httpx
from entitysdk.models.execution import Execution
from entitysdk.types import ContentType, ExecutorType
from fastapi import APIRouter, Depends

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client as get_db_client
from app.dependencies.launchsystem import get_client as get_ls_client
from app.logger import L

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])

"""Path to the obi-one repository"""
OBI_ONE_REPO = "https://github.com/openbraininstitute/obi-one.git"

"""Path to launch script within the repository. Must contain code.py and requirements.txt."""
OBI_ONE_LAUNCH_PATH = "launch_scripts/launch_task_for_single_config_asset"

"""Commit hash of the code version to use."""
OBI_ONE_COMMIT_SHA = "11bad06f5433eb13f47aa086c79048ca043e9a04"


class TaskConfigType(StrEnum):
    """List of entitycore config types supported for job submission."""

    CIRCUIT_EXTRACTION = entitysdk.models.CircuitExtractionConfig.__name__


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


def _get_execution_activity_type(config_entity_type: str) -> str:
    """Determines the execution activity for a given config entity type."""
    type_key = config_entity_type.replace("Config", "")
    all_models = [
        _name
        for _name in dir(entitysdk.models)
        if hasattr(getattr(entitysdk.models, _name), "__base__")
    ]
    exec_models = [
        _name for _name in all_models if getattr(entitysdk.models, _name).__base__ == Execution
    ]
    exec_model = [_name for _name in exec_models if type_key in _name]
    if len(exec_model) != 1:
        msg = (
            f"Execution activity for '{config_entity_type}' could not be determined "
            f"({len(exec_model)} found)!"
        )
        raise ValueError(msg)
    return exec_model[0]


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


def _submit_task_job(
    db_client: entitysdk.Client,
    ls_client: httpx.Client,
    entity_type: TaskConfigType,
    entity_id: str,
    config_asset_id: str,
) -> str | None:
    """Creates an activity and submits a task as a job on the launch-system."""
    if not db_client.project_context:
        msg = "Project context is required!"
        raise ValueError(msg)
    project_id = str(db_client.project_context.project_id)
    virtual_lab_id = str(db_client.project_context.virtual_lab_id)

    # Create activity and set to pending for launching the job
    activity_type = _get_execution_activity_type(entity_type)
    activity_id = _create_execution_activity(db_client, activity_type, activity_type, entity_id)
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
    job_data = {
        "resources": {"cores": 1, "memory": 2, "timelimit": time_limit},
        "code": {
            "type": "python_repository",
            "location": OBI_ONE_REPO,
            "commit": OBI_ONE_COMMIT_SHA,
            "path": str(Path(OBI_ONE_LAUNCH_PATH) / "code.py"),
            "dependencies": str(Path(OBI_ONE_LAUNCH_PATH) / "requirements.txt"),
        },
        "invocation": f"code::path {' '.join(cmd_args)}",
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

    return activity_id


@router.get(
    "/task-launch",
    summary="Task launch",
    description=(
        "Launches an obi-one task as a dedicated job on the launch-system. "
        "The type of task is determined based on the config entity provided."
    ),
)
def task_launch_endpoint(
    entity_type: TaskConfigType,
    entity_id: str,
    db_client: Annotated[entitysdk.Client, Depends(get_db_client)],
    ls_client: Annotated[httpx.Client, Depends(get_ls_client)],
) -> str | None:
    activity_id = None

    # Determine config asset
    config_asset_id = _get_config_asset(db_client, entity_type, entity_id)

    # Launch task
    activity_id = _submit_task_job(db_client, ls_client, entity_type, entity_id, config_asset_id)

    return activity_id
