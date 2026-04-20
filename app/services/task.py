import json
from uuid import UUID

import entitysdk
import httpx
import libsonata
from entitysdk import ProjectContext, models
from entitysdk.types import ActivityStatus, AssetLabel, CircuitScale, ExecutorType

import app.services.resource_estimation.circuit_extraction
import app.services.resource_estimation.circuit_simulation
from app.config import settings
from app.logger import L
from app.schemas.callback import CallBack, HttpRequestCallBackConfig
from app.schemas.task import (
    Resources,
    TaskDefinition,
    TaskDefinitionLegacy,
    TaskLaunchInfo,
    TaskLaunchSubmit,
)
from app.types import CallBackAction, CallBackEvent, TargetSimulator, TaskType
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
) -> TaskLaunchInfo:
    """Creates an activity and submits a task as a job on the launch-system."""
    # TODO: Remove once simulations are migrated to generic configs
    if isinstance(task_definition, TaskDefinitionLegacy):
        config_type = task_definition.config_type
        config = db_client.get_entity(entity_id=config_id, entity_type=config_type)
        activity_type = task_definition.activity_type
        activity_id = db_sdk.create_activity(
            client=db_client,
            used=[config],
            activity_status=ActivityStatus.pending,
            activity_type=activity_type,
        ).id
    else:
        config_type = models.TaskConfig
        config = db_client.get_entity(entity_id=config_id, entity_type=config_type)
        activity_type = models.TaskActivity
        activity_id = db_sdk.create_generic_activity(
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
        case TaskType.circuit_simulation_neurodamus_cluster:
            executor_type = ExecutorType.distributed_job
            job_data = _circuit_simulation_job_data(
                simulation_id=config_id,
                simulation_execution_id=activity_id,
                project_id=project_context.project_id,
                callbacks=all_callbacks,
                task_definition=task_definition,
            )
        case _:
            executor_type = ExecutorType.single_node_job
            job_data = _generic_job_data(
                entity_cache=True,
                config_id=config_id,
                activity_id=activity_id,
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
            activity_type=activity_type,
            status=ActivityStatus.error,
        )
        msg = f"Job submission failed!\n{json.loads(response.text)}"
        raise RuntimeError(msg)
    response_body = response.json()
    job_id = response_body["id"]
    L.info(f"Job submitted (ID {job_id})")

    db_sdk.update_activity_executor(
        client=db_client,
        activity_id=activity_id,
        activity_type=activity_type,
        execution_id=job_id,
        executor=executor_type,
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
    resources = task_definition.resources.model_dump(mode="json")
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
) -> dict:
    resources = task_definition.resources.model_dump(mode="json")

    if isinstance(task_definition, TaskDefinitionLegacy):
        inputs = [
            f"--task-type {task_definition.task_type}",
            f"--config_entity_type {task_definition.config_type_name}",
            f"--config_entity_id {config_id}",
            f"--entity_cache {entity_cache}",
            f"--scan_output_root {output_root}",
            f"--virtual_lab_id {virtual_lab_id}",
            f"--project_id {project_id}",
            f"--execution_activity_type {task_definition.activity_type_name}",
            f"--execution_activity_id {activity_id}",
        ]
    else:
        inputs = [
            f"--task-type {task_definition.task_type}",
            f"--config_entity_id {config_id}",
            f"--entity_cache {entity_cache}",
            f"--scan_output_root {output_root}",
            f"--virtual_lab_id {virtual_lab_id}",
            f"--project_id {project_id}",
            f"--execution_activity_id {activity_id}",
        ]

    return {
        "code": task_definition.code.model_dump(mode="json"),
        "resources": resources,
        "inputs": inputs,
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
    # TODO: Remove once simulations are migrated to generic configs
    if isinstance(task_definition, TaskDefinitionLegacy):
        task_activity_type = task_definition.activity_type
    else:
        task_activity_type = models.TaskActivity

    current_status = db_client.get_entity(
        entity_id=activity_id, entity_type=task_activity_type
    ).status

    if current_status != ActivityStatus.done:
        db_sdk.update_activity_status(
            client=db_client,
            activity_id=activity_id,
            activity_type=task_activity_type,
            status=ActivityStatus.error,
        )


def estimate_task_resources(
    json_model: TaskLaunchSubmit,
    db_client: entitysdk.Client,
    task_definition: TaskDefinition,
    compute_cell: str,
) -> Resources:
    """Estimates the machine resources for a given task."""
    match task_definition.task_type:
        case TaskType.circuit_extraction:
            return app.services.resource_estimation.circuit_extraction.estimate_task_resources(
                json_model=json_model,
                db_client=db_client,
                task_definition=task_definition,
                compute_cell=compute_cell,
            )
        case TaskType.circuit_simulation_neuron:
            return app.services.resource_estimation.circuit_simulation.estimate_task_resources(
                json_model=json_model,
                db_client=db_client,
                task_definition=task_definition,
                compute_cell=compute_cell,
            )
        case TaskType.circuit_simulation_neurodamus_cluster:
            return app.services.resource_estimation.circuit_simulation.estimate_task_resources(
                json_model=json_model,
                db_client=db_client,
                task_definition=task_definition,
                compute_cell=compute_cell,
            )
        case TaskType.circuit_simulation_inait_machine:
            return app.services.resource_estimation.circuit_simulation.estimate_task_resources(
                json_model=json_model,
                db_client=db_client,
                task_definition=task_definition,
                compute_cell=compute_cell,
            )
        case _:
            return task_definition.resources.model_copy(update={"compute_cell": compute_cell})


def select_simulation_task(
    *, db_client: entitysdk.Client, config_id: UUID, config_type: models.Entity
) -> TaskType:
    simulation = db_client.get_entity(entity_id=config_id, entity_type=config_type)
    sim_config_content = db_client.fetch_assets(
        entity=simulation,
        selection={
            "label": AssetLabel.simulation_config,
        },
    ).one()
    simulation_config = libsonata.SimulationConfig(sim_config_content, ".")
    target_simulator = TargetSimulator(simulation_config.target_simulator.name)

    circuit = db_client.get_entity(
        entity_id=simulation_config.entity_id, entity_type=models.Circuit
    )

    circuit_config = db_sdk.get_json_asset_content(
        client=db_client,
        entity=circuit,
        selection={
            "label": AssetLabel.circuit_config,
        },
    )
    target_simulator_circuit = circuit_config.get("target_simulator", TargetSimulator.NEURON)

    circuit_scale = circuit.circuit_scale
    assert target_simulator == target_simulator_circuit

    match target_simulator:
        case TargetSimulator.LEARNING_ENGINE:
            return TaskType.circuit_simulation_inait_machine
        case TargetSimulator.NEURON | TargetSimulator.CORENEURON:
            match circuit_scale:
                case CircuitScale.single | CircuitScale.pair | CircuitScale.small:
                    return TaskType.circuit_simulation_neuron
                case _:
                    return TaskType.circuit_simulation_neurodamus_cluster
        case _:
            msg = f"Unsupported target simulator {target_simulator}"
            raise RuntimeError(msg)
