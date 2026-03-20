import json
from uuid import UUID

import entitysdk
import httpx
import numpy as np
from entitysdk import ProjectContext
from entitysdk.types import ActivityStatus, ExecutorType

from app.config import settings
from app.logger import L
from app.schemas.callback import CallBack, HttpRequestCallBackConfig
from app.schemas.task import TaskDefinition, TaskLaunchInfo, TaskLaunchSubmit
from app.types import CallBackAction, CallBackEvent, TaskType
from obi_one import deserialize_obi_object_from_json_data
from obi_one.scientific.library.circuit_metrics import (
    CircuitStatsLevelOfDetail,
    get_circuit_metrics,
)
from obi_one.scientific.unions.config_task_map import get_task_type_config_asset_label
from obi_one.utils import db_sdk


def submit_task_job(
    *,
    db_client: entitysdk.Client,
    ls_client: httpx.Client,
    config_id: UUID,
    task_definition: TaskDefinition,
    project_context: entitysdk.ProjectContext,
    callback_url: str,
    callbacks: list[CallBack],
    compute_cell: str,
) -> TaskLaunchInfo:
    """Creates an activity and submits a task as a job on the launch-system."""
    config = db_client.get_entity(
        entity_id=config_id,
        entity_type=task_definition.config_type,
    )
    activity_id = db_sdk.create_activity(
        client=db_client,
        used=[config],
        activity_status=ActivityStatus.pending,
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
                compute_cell=compute_cell,
            )
        case _:
            job_data = _generic_job_data(
                entity_cache=True,
                config_id=config_id,
                activity_id=activity_id,
                callbacks=all_callbacks,
                compute_cell=compute_cell,
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
    compute_cell: str,
) -> dict:
    resources = task_definition.resources.model_dump(mode="json") | {"compute_cell": compute_cell}
    return {
        "code": task_definition.code.model_dump(mode="json"),
        "resources": resources,
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
    entity_cache: bool,
    output_root: str,
    callbacks: list[CallBack],
    task_definition: TaskDefinition,
    compute_cell: str,
) -> dict:
    resources = task_definition.resources.model_dump(mode="json") | {"compute_cell": compute_cell}
    return {
        "code": task_definition.code.model_dump(mode="json"),
        "resources": resources,
        "inputs": [
            f"--task-type {task_definition.task_type}",
            f"--config_entity_type {task_definition.config_type_name}",
            f"--config_entity_id {config_id}",
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

    if current_status != ActivityStatus.done:
        db_client.update_entity(
            entity_id=activity_id,
            entity_type=task_definition.activity_type,
            attrs_or_entity={"status": ActivityStatus.error},
        )


def _get_required_cpu_memory_combo(mem_gb_required: float) -> tuple[int, int]:
    """Returns the required CPU/memory combination."""
    # From launch-system
    cpu_memory_combinations: dict[int, set[int]] = {
        1: {2, 4, 6, 8},
        2: {4, 8, 12, 16},
        4: {8, 16, 24, 30},
        8: {16, 32, 48, 60},
        16: {32, 64, 96, 120},
    }

    max_mem = 0
    for ncpu, mem_values in cpu_memory_combinations.items():
        for mem in sorted(mem_values):
            max_mem = max(max_mem, mem)
            if mem > mem_gb_required:
                return (ncpu, mem)
    msg = (
        f"No CPU/memory combination found"
        f" (required: {mem_gb_required:.1f} GB, available: {max_mem:.1f} GB)!"
    )
    raise ValueError(msg)


def _check_available_disk_space(disk_space_gb_required: float) -> None:
    """Checks if the required disk space is available."""
    # From launch-system
    disk_space_limit_gb = 20

    if disk_space_gb_required > disk_space_limit_gb:
        msg = (
            f"Not enough disk space"
            f" (required: {disk_space_gb_required:.1f} GB,"
            f" available: {disk_space_limit_gb:.1f} GB)!"
        )
        raise ValueError(msg)


def update_resources(  # noqa: PLR0914
    json_model: TaskLaunchSubmit, db_client: entitysdk.Client, task_definition: TaskDefinition
) -> TaskDefinition:
    """Updates the machine resources in the task definition."""
    match task_definition.task_type:
        case TaskType.circuit_extraction:
            # Get extraction config
            config = db_client.get_entity(
                entity_id=json_model.config_id,
                entity_type=task_definition.config_type,
            )
            config_asset_id = db_sdk.get_entity_asset_by_label(
                client=db_client,
                config=config,
                asset_label=get_task_type_config_asset_label(task_definition.task_type),
            ).id

            json_str = db_client.download_content(
                entity_id=json_model.config_id,
                entity_type=task_definition.config_type,
                asset_id=config_asset_id,
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

            # Estimate memory based on the number of input neurons
            nbio = np.sum(
                [npop.number_of_nodes for npop in circuit_metrics.biophysical_node_populations]
            )
            nvirt = np.sum(
                [npop.number_of_nodes for npop in circuit_metrics.virtual_node_populations]
            )
            input_size_neurons = (nbio + nvirt) if single_config.initialize.do_virtual else nbio

            mem_gb_required = 1 + 55e-6 * input_size_neurons
            ncpu, mem_gb = _get_required_cpu_memory_combo(mem_gb_required)

            # Estimate time limit based on the number input neurons
            time_h = np.ceil(input_size_neurons * 5e-6).astype(int)

            # Estimate disk space based in the number of input synapses
            sbio = np.sum(
                [
                    epop.number_of_edges
                    for epop in circuit_metrics.chemical_edge_populations
                    if epop.source_name in circuit_metrics.names_of_biophys_node_populations
                ]
            )
            svirt = np.sum(
                [
                    epop.number_of_edges
                    for epop in circuit_metrics.chemical_edge_populations
                    if epop.source_name in circuit_metrics.names_of_virtual_node_populations
                ]
            )
            input_size_synapses = (sbio + svirt) if single_config.initialize.do_virtual else sbio
            output_size_synapses = input_size_synapses  # Using maximum output count
            output_size_gb = 1 + output_size_synapses * 1.85e-7
            _check_available_disk_space(output_size_gb)

            # Update resources
            updated_resources = task_definition.resources.model_copy(
                update={"cores": ncpu, "memory": mem_gb, "timelimit": f"{time_h:02d}:00"}
            )
            task_definition = task_definition.model_copy(update={"resources": updated_resources})

        case _:
            # Don't update anything
            pass
    return task_definition
