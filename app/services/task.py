import json
from uuid import UUID

import entitysdk
import httpx
from entitysdk import ProjectContext
from entitysdk.types import ExecutorType

from app.config import settings
from app.logger import L
from app.schemas.callback import CallBack, HttpRequestCallBackConfig
from app.schemas.task import TaskDefinition, TaskLaunchInfo
from app.types import CallBackAction, CallBackEvent, TaskType
from app.utils import db_sdk


def submit_task_job(
    *,
    db_client: entitysdk.Client,
    ls_client: httpx.Client,
    config_id: UUID,
    task_definition: TaskDefinition,
    project_context: entitysdk.ProjectContext,
    callback_url: str,
    callbacks: list[CallBack],
) -> TaskLaunchInfo:
    """Creates an activity and submits a task as a job on the launch-system."""
    config = db_client.get_entity(
        entity_id=config_id,
        entity_type=task_definition.config_type,
    )
    activity_id = db_sdk.create_activity(
        client=db_client,
        used=[config],
        activity_status="pending",
        activity_type=task_definition.activity_type,
    ).id
    failure_callback = _generate_failure_callback(
        activity_id=activity_id,
        task_type=task_definition.task_type,
        callback_url=callback_url,
        project_context=project_context,
    )
    all_callbacks = [failure_callback, *callbacks]

    match task_definition.task_type:
        case TaskType.circuit_simulation:
            job_data = _circuit_simulation_job_data(
                simulation_id=config_id,
                simulation_execution_id=activity_id,
                project_id=project_context.project_id,
                callbacks=all_callbacks,
                task_definition=task_definition,
            )
        case _:
            config_asset_id = db_sdk.get_config_asset(
                client=db_client,
                config=config,
                asset_label=task_definition.config_asset_label,
            ).id
            job_data = _generic_job_data(
                entity_cache=True,
                config_id=config_id,
                activity_id=activity_id,
                config_asset_id=config_asset_id,
                callbacks=all_callbacks,
                task_definition=task_definition,
                project_id=project_context.project_id,
                virtual_lab_id=project_context.virtual_lab_id,
                output_root=settings.LAUNCH_SYSTEM_OUTPUT_DIR,
            )

    # Submit job
    response = ls_client.post(url="/job", json=job_data)
    if not response.is_success:
        db_sdk.update_activity_status(
            client=db_client,
            activity_id=activity_id,
            activity_type=task_definition.activity_type,
            status="error",
        )
        msg = f"Job submission failed!\n{json.loads(response.text)}"
        raise RuntimeError(msg)
    response_body = response.json()
    job_id = response_body["id"]
    L.info(f"Job submitted (ID {job_id})")

    db_sdk.update_activity_executor(
        client=db_client,
        activity_id=activity_id,
        activity_type=task_definition.activity_type,
        execution_id=job_id,
        executor=ExecutorType.single_node_job,
    )
    return TaskLaunchInfo(
        task_type=task_definition.task_type,
        config_id=config_id,
        activity_id=activity_id,
        job_id=job_id,
    )


def _circuit_simulation_job_data(
    *,
    simulation_id: UUID,
    simulation_execution_id: UUID,
    project_id: UUID,
    callbacks: list[CallBack],
    task_definition: TaskDefinition,
) -> dict:
    return {
        "type": "circuit_simulation",
        "code": task_definition.code,
        "resources": task_definition.resources,
        "inputs": [
            "--simulation-id",
            str(simulation_id),
            "--simulation-execution-id",
            str(simulation_execution_id),
        ],
        "project_id": str(project_id),
        "callbacks": [c.model_dump(mode="json") for c in callbacks],
    }


def _generic_job_data(
    *,
    config_id: UUID,
    activity_id: UUID,
    project_id: UUID,
    virtual_lab_id: UUID,
    config_asset_id: UUID,
    entity_cache: bool,
    output_root: str,
    callbacks: list[CallBack],
    task_definition: TaskDefinition,
) -> dict:
    return {
        "type": "generic",
        "code": task_definition.code,
        "resources": task_definition.resources,
        "inputs": [
            f"--entity_type {task_definition.config_type_name}",
            f"--entity_id {config_id}",
            f"--config_asset_id {config_asset_id}",
            f"--entity_cache {entity_cache}",
            f"--scan_output_root {output_root}",
            f"--virtual_lab_id {virtual_lab_id}",
            f"--project_id {project_id}",
            f"--execution_activity_type {task_definition.activity_type_name}",
            f"--execution_activity_id {activity_id}",
        ],
        "project_id": str(project_id),
        "callbacks": [c.model_dump(mode="json") for c in callbacks],
    }


def _generate_failure_callback(
    *,
    callback_url: str,
    task_type: TaskType,
    activity_id: UUID,
    project_context: ProjectContext,
) -> CallBack:
    """Builds the callback URL for task failure notifications."""
    config = HttpRequestCallBackConfig(
        url=f"{callback_url}/failure",
        method="POST",
        params={
            "task_type": task_type,
            "activity_id": str(activity_id),
        },
        headers={
            "virtual-lab-id": str(project_context.virtual_lab_id),
            "project-id": str(project_context.project_id),
        },
    )
    return CallBack(
        event_type=CallBackEvent.job_on_failure,
        action_type=CallBackAction.http_request_with_token,
        config=config,
    )


def handle_task_failure_callback(
    *,
    activity_id: UUID,
    db_client: entitysdk.Client,
    task_definition: TaskDefinition,
) -> None:
    current_status = db_client.get_entity(
        entity_id=activity_id,
        entity_type=task_definition.activity_type,
    ).status

    if current_status != "done":
        db_client.update_entity(
            entity_id=activity_id,
            entity_type=task_definition.activity_type,
            attrs_or_entity={"status": "error"},
        )
