import json
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path
from typing import Annotated

import entitysdk
import httpx
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

    CIRCUIT_EXTRACTION = "CircuitExtractionConfig"


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

    # Create activity
    # TODO
    activity_id = None

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
    ]
    if activity_id:
        cmd_args.append(f"--activity_id {activity_id}")

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
        msg = f"Job submission failed!\n{json.loads(response.text)}"
        raise RuntimeError(msg)
    response_body = response.json()
    job_id = response_body["id"]
    L.info(f"Job submitted (ID {job_id})")

    # Add job as executor to activity
    # TODO
    activity_id = job_id  # For now, return job ID

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
    config_asset_id: str,
    db_client: Annotated[entitysdk.Client, Depends(get_db_client)],
    ls_client: Annotated[httpx.Client, Depends(get_ls_client)],
) -> str | None:
    activity_id = None

    # Launch task
    activity_id = _submit_task_job(db_client, ls_client, entity_type, entity_id, config_asset_id)

    return activity_id
