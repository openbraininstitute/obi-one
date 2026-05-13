import json
from datetime import UTC, datetime
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import entitysdk
import httpx
import libsonata
import pytest
from entitysdk.types import AssetLabel, TaskActivityType, TaskConfigType

import app.services.resource_estimation.circuit_simulation
from app.errors import ApiError, ApiErrorCode
from app.mappings import TASK_DEFINITIONS
from app.schemas.callback import CallBack, CallBackAction, CallBackEvent, HttpRequestCallBackConfig
from app.schemas.cluster import ClusterInstanceInfo
from app.schemas.task import MachineResources, TaskLaunchSubmit, TaskType
from app.services import task as test_module

from tests.utils import PROJECT_ID, VIRTUAL_LAB_ID

ASSET_ID = uuid4()

TASK_TYPES = [task_type for task_type in TaskType if task_type != TaskType.circuit_simulation]


@pytest.fixture
def db_client():
    """Database client."""
    return entitysdk.Client(api_url="http://my-url", token_manager="my-token")  # noqa: S106


@pytest.fixture
def ls_client():
    """Launch system client."""
    return httpx.Client(base_url="http://my-launch-system-url")


@pytest.fixture
def config_id():
    return uuid4()


@pytest.fixture
def activity_id():
    return uuid4()


@pytest.fixture
def callbacks(activity_id):
    config = HttpRequestCallBackConfig(
        url="http://failure",
        method="POST",
        params={
            "task_type": TaskType.circuit_simulation_neurodamus_cluster,
            "activity_id": str(activity_id),
        },
        headers={
            "virtual-lab-id": str(VIRTUAL_LAB_ID),
            "project-id": str(PROJECT_ID),
        },
    )
    return [
        CallBack(
            event_type=CallBackEvent.job_on_failure,
            action_type=CallBackAction.http_request_with_token,
            config=config,
        )
    ]


@pytest.mark.parametrize(
    ("task_type", "config_route", "config_response", "activity_route", "activity_response"),
    [
        (
            TaskType.circuit_extraction,
            "task-config",
            {
                "circuit_id": str(uuid4()),
                "scan_parameters": {},
                "task_config_type": TaskConfigType.circuit_extraction__config,
                "meta": {},
                "assets": [
                    {
                        "id": str(ASSET_ID),
                        "label": AssetLabel.circuit_extraction_config,
                        "path": "foo.txt",
                        "full_path": "/foo.txt",
                        "size": 0,
                        "storage_type": "aws_s3_internal",
                        "is_directory": True,
                        "content_type": "application/json",
                    },
                ],
            },
            "task-activity",
            {
                "task_activity_type": TaskActivityType.circuit_extraction__execution,
            },
        ),
        (
            TaskType.circuit_simulation_neurodamus_cluster,
            "simulation",
            {
                "entity_id": str(uuid4()),
                "simulation_campaign_id": str(uuid4()),
                "scan_parameters": {},
            },
            "simulation-execution",
            {},
        ),
        (
            TaskType.circuit_simulation_brian2_machine,
            "simulation",
            {
                "entity_id": str(uuid4()),
                "simulation_campaign_id": str(uuid4()),
                "scan_parameters": {},
            },
            "simulation-execution",
            {},
        ),
    ],
)
def test_submit_task_job__success(
    task_type,
    config_route,
    config_response,
    activity_route,
    activity_response,
    db_client,
    ls_client,
    project_context,
    httpx_mock,
):
    job_id = uuid4()
    config_id = uuid4()
    activity_id = uuid4()
    callback_url = "http://my-callback-url"

    httpx_mock.add_response(
        url=f"http://my-url/{config_route}/{config_id}",
        method="GET",
        json=config_response | {"id": str(config_id)},
    )
    httpx_mock.add_callback(
        lambda request: httpx.Response(
            status_code=200,
            json=json.loads(request.content) | activity_response | {"id": str(activity_id)},
        ),
        url=f"http://my-url/{activity_route}",
        method="POST",
    )
    httpx_mock.add_callback(
        lambda request: httpx.Response(
            status_code=200,
            json=json.loads(request.content) | {"id": str(job_id)},
        ),
        url="http://my-launch-system-url/job",
        method="POST",
    )
    httpx_mock.add_callback(
        lambda request: httpx.Response(
            status_code=200,
            json={
                "id": str(activity_id),
                "start_time": datetime.now(UTC).isoformat(),
                "status": "pending",
            }
            | activity_response
            | json.loads(request.content),
        ),
        url=f"http://my-url/{activity_route}/{activity_id}",
        method="PATCH",
    )
    res = test_module.submit_task_job(
        config_id=config_id,
        db_client=db_client,
        ls_client=ls_client,
        task_definition=TASK_DEFINITIONS[task_type],
        project_context=project_context,
        callback_url=callback_url,
        callbacks=[],
    )
    assert res.task_type == task_type
    assert res.config_id == config_id
    assert res.activity_id == activity_id
    assert res.job_id == job_id


@pytest.mark.parametrize(
    ("task_type", "config_route", "config_response", "activity_route", "activity_response"),
    [
        (
            TaskType.circuit_extraction,
            "task-config",
            {
                "circuit_id": str(uuid4()),
                "scan_parameters": {},
                "assets": [
                    {
                        "id": str(ASSET_ID),
                        "label": AssetLabel.circuit_extraction_config,
                        "path": "foo.txt",
                        "full_path": "/foo.txt",
                        "size": 0,
                        "storage_type": "aws_s3_internal",
                        "is_directory": True,
                        "content_type": "application/json",
                    },
                ],
                "task_config_type": TaskConfigType.circuit_extraction__config,
                "meta": {},
            },
            "task-activity",
            {
                "task_activity_type": TaskActivityType.circuit_extraction__execution,
            },
        ),
        (
            TaskType.circuit_simulation_neurodamus_cluster,
            "simulation",
            {
                "entity_id": str(uuid4()),
                "simulation_campaign_id": str(uuid4()),
                "scan_parameters": {},
            },
            "simulation-execution",
            {},
        ),
        (
            TaskType.circuit_simulation_brian2_machine,
            "simulation",
            {
                "entity_id": str(uuid4()),
                "simulation_campaign_id": str(uuid4()),
                "scan_parameters": {},
            },
            "simulation-execution",
            {},
        ),
    ],
)
def test_submit_task_job__failure(
    task_type,
    config_route,
    config_response,
    activity_route,
    activity_response,
    db_client,
    ls_client,
    project_context,
    httpx_mock,
):
    config_id = uuid4()
    activity_id = uuid4()
    callback_url = "http://my-callback-url"

    httpx_mock.add_response(
        url=f"http://my-url/{config_route}/{config_id}",
        method="GET",
        json=config_response | {"id": str(config_id)},
    )
    httpx_mock.add_callback(
        lambda request: httpx.Response(
            status_code=200,
            json=json.loads(request.content) | activity_response | {"id": str(activity_id)},
        ),
        url=f"http://my-url/{activity_route}",
        method="POST",
    )
    httpx_mock.add_callback(
        lambda request: httpx.Response(
            status_code=500,
            json=json.loads(request.content),
        ),
        url="http://my-launch-system-url/job",
        method="POST",
    )
    httpx_mock.add_callback(
        lambda request: httpx.Response(
            status_code=200,
            json={
                "id": str(activity_id),
                "start_time": datetime.now(UTC).isoformat(),
                "status": "pending",
            }
            | activity_response
            | json.loads(request.content),
        ),
        url=f"http://my-url/{activity_route}/{activity_id}",
        method="PATCH",
    )

    with pytest.raises(RuntimeError, match="Job submission failed"):
        test_module.submit_task_job(
            config_id=config_id,
            db_client=db_client,
            ls_client=ls_client,
            task_definition=TASK_DEFINITIONS[task_type],
            project_context=project_context,
            callback_url=callback_url,
            callbacks=[],
        )


def test_inait_job_data(config_id, activity_id, callbacks):
    task_type = TaskType.circuit_simulation_inait_machine
    task_definition = TASK_DEFINITIONS[task_type]

    res = test_module._inait_job_data(
        simulation_id=config_id,
        simulation_execution_id=activity_id,
        project_id=PROJECT_ID,
        virtual_lab_id=VIRTUAL_LAB_ID,
        callbacks=callbacks,
        task_definition=task_definition,
    )

    assert res == {
        "code": {
            "type": "python_repository",
            "location": "https://github.com/openbraininstitute-partners/inait",
            "ref": "commit:54da893cbf445a9c28b1a116ae8b8d7d4ed8a6dd",
            "path": "scripts/simulate-circuits/run.py",
            "dependencies": "scripts/simulate-circuits/requirements.txt",
            "capabilities": {"private_packages": False, "env_secrets": []},
            "staged_directories": ["wheels", "scripts/simulate-circuits/"],
        },
        "resources": {
            "type": "machine",
            "cores": 1,
            "memory": 8,
            "compute_cell": "local",
            "timelimit": "02:00",
        },
        "inputs": [
            "sonata-simulation-task",
            f" --project-id {PROJECT_ID}",
            f" --virtual-lab-id {VIRTUAL_LAB_ID}",
            f" --simulation-id {config_id}",
            f" --simulation-execution-id {activity_id}",
        ],
        "project_id": PROJECT_ID,
        "callbacks": [
            {
                "action_type": "http_request_with_token",
                "event_type": "job_on_failure",
                "config": {
                    "url": "http://failure",
                    "method": "POST",
                    "params": {
                        "task_type": "circuit_simulation_neurodamus_cluster",
                        "activity_id": str(activity_id),
                    },
                    "headers": {
                        "virtual-lab-id": VIRTUAL_LAB_ID,
                        "project-id": PROJECT_ID,
                    },
                    "payload": None,
                },
            }
        ],
    }


def test_brian2_job_data(config_id, activity_id, callbacks):
    task_type = TaskType.circuit_simulation_brian2_machine
    task_definition = TASK_DEFINITIONS[task_type]

    res = test_module._brian2_job_data(
        simulation_id=config_id,
        simulation_execution_id=activity_id,
        project_id=PROJECT_ID,
        virtual_lab_id=VIRTUAL_LAB_ID,
        callbacks=callbacks,
        task_definition=task_definition,
    )

    assert res == {
        "code": {
            "type": "python_repository",
            "location": task_definition.code.location,
            "ref": "commit:b3e8670db32d26e9fa4c71d79d6f6de46b61cb16",
            "path": "examples/J_drosophila/simulate-brian2.py",
            "dependencies": "examples/J_drosophila/requirements.txt",
            "capabilities": {"private_packages": False, "env_secrets": []},
            "staged_directories": [],
        },
        "resources": {
            "type": "machine",
            "cores": 1,
            "memory": 8,
            "compute_cell": "local",
            "timelimit": "02:00",
        },
        "inputs": [
            "sonata-simulation-task",
            f" --project-id {PROJECT_ID}",
            f" --virtual-lab-id {VIRTUAL_LAB_ID}",
            f" --simulation-id {config_id}",
            f" --simulation-execution-id {activity_id}",
        ],
        "project_id": PROJECT_ID,
        "callbacks": [
            {
                "action_type": "http_request_with_token",
                "event_type": "job_on_failure",
                "config": {
                    "url": "http://failure",
                    "method": "POST",
                    "params": {
                        "task_type": "circuit_simulation_neurodamus_cluster",
                        "activity_id": str(activity_id),
                    },
                    "headers": {
                        "virtual-lab-id": VIRTUAL_LAB_ID,
                        "project-id": PROJECT_ID,
                    },
                    "payload": None,
                },
            }
        ],
    }


def test_circuit_simulation_job_data(config_id, activity_id, callbacks):
    task_type = TaskType.circuit_simulation_neurodamus_cluster

    task_definition = TASK_DEFINITIONS[task_type]

    res = test_module._circuit_simulation_job_data(
        simulation_id=config_id,
        simulation_execution_id=activity_id,
        project_id=PROJECT_ID,
        callbacks=callbacks,
        task_definition=task_definition,
    )

    assert res == {
        "resources": {
            "type": "cluster",
            "instances": 1,
            "instance_type": "small",
            "timelimit": None,
            "compute_cell": "local",
        },
        "inputs": [
            "--simulation-id",
            str(config_id),
            "--simulation-execution-id",
            str(activity_id),
        ],
        "code": {
            "type": "builtin",
            "script": "circuit_simulation",
        },
        "project_id": PROJECT_ID,
        "callbacks": [
            {
                "action_type": "http_request_with_token",
                "event_type": "job_on_failure",
                "config": {
                    "url": "http://failure",
                    "method": "POST",
                    "params": {
                        "task_type": task_type,
                        "activity_id": str(activity_id),
                    },
                    "headers": {
                        "virtual-lab-id": VIRTUAL_LAB_ID,
                        "project-id": PROJECT_ID,
                    },
                    "payload": None,
                },
            }
        ],
    }


def test_generic_job_data(config_id, activity_id, callbacks):
    task_definition = TASK_DEFINITIONS["circuit_extraction"]

    res = test_module._generic_job_data(
        config_id=config_id,
        activity_id=activity_id,
        project_id=UUID(PROJECT_ID),
        virtual_lab_id=UUID(VIRTUAL_LAB_ID),
        task_definition=task_definition,
        entity_cache=True,
        output_root="/foo",
        callbacks=callbacks,
    )

    assert res == {
        "resources": {
            "type": "machine",
            "cores": 1,
            "memory": 2,
            "timelimit": "00:10",
            "compute_cell": "local",
        },
        "code": {
            "type": "python_repository",
            "location": "https://github.com/openbraininstitute/obi-one.git",
            "ref": task_definition.code.ref,
            "path": "launch_scripts/launch_task_for_single_config_asset/main.py",
            "dependencies": (
                "launch_scripts/launch_task_for_single_config_asset/dependencies"
                "/circuit_extraction.txt"
            ),
            "capabilities": {
                "private_packages": False,
                "env_secrets": [],
            },
            "staged_directories": [],
        },
        "inputs": [
            "--task-type circuit_extraction",
            f"--config_entity_id {config_id}",
            "--entity_cache True",
            "--scan_output_root /foo",
            f"--virtual_lab_id {VIRTUAL_LAB_ID}",
            f"--project_id {PROJECT_ID}",
            f"--execution_activity_id {activity_id}",
        ],
        "project_id": PROJECT_ID,
        "callbacks": [
            {
                "action_type": "http_request_with_token",
                "event_type": "job_on_failure",
                "config": {
                    "url": "http://failure",
                    "method": "POST",
                    "params": {
                        "task_type": "circuit_simulation_neurodamus_cluster",
                        "activity_id": str(activity_id),
                    },
                    "headers": {
                        "virtual-lab-id": VIRTUAL_LAB_ID,
                        "project-id": PROJECT_ID,
                    },
                    "payload": None,
                },
            }
        ],
    }


def test_generic_job_data_legacy(config_id, activity_id, callbacks):
    task_definition = TASK_DEFINITIONS[TaskType.circuit_simulation_neuron]

    res = test_module._generic_job_data(
        config_id=config_id,
        activity_id=activity_id,
        project_id=UUID(PROJECT_ID),
        virtual_lab_id=UUID(VIRTUAL_LAB_ID),
        task_definition=task_definition,
        entity_cache=True,
        output_root="/foo",
        callbacks=callbacks,
    )

    assert f"--config_entity_type {task_definition.config_type_name}" in res["inputs"]
    assert f"--execution_activity_type {task_definition.activity_type_name}" in res["inputs"]
    assert f"--execution_activity_id {activity_id}" in res["inputs"]


def test_generate_failure_callback(project_context, activity_id):
    res = test_module._generate_failure_callback(
        callback_url="my-callback-url",
        task_type="circuit_extraction",
        activity_id=activity_id,
        project_context=project_context,
    )

    assert res.event_type == CallBackEvent.job_on_failure
    assert res.action_type == CallBackAction.http_request_with_token
    assert res.config.url == "my-callback-url/failure"
    assert res.config.method == "POST"
    assert res.config.params == {"task_type": "circuit_extraction", "activity_id": str(activity_id)}


@pytest.mark.parametrize(
    ("task_type", "activity_route", "activity_response"),
    [
        (
            TaskType.circuit_extraction,
            "task-activity",
            {"task_activity_type": TaskActivityType.circuit_extraction__execution},
        ),
        (TaskType.circuit_simulation_neurodamus_cluster, "simulation-execution", {}),
    ],
)
def test_handle_task_failure_callback(
    db_client, task_type, activity_route, activity_response, httpx_mock
):
    activity_id = uuid4()
    activity_payload = {
        "id": str(activity_id),
        "status": "running",
        "start_time": datetime.now(UTC).isoformat(),
    }
    httpx_mock.add_response(
        url=f"http://my-url/{activity_route}/{activity_id}",
        method="GET",
        json=activity_payload | activity_response,
    )
    httpx_mock.add_callback(
        lambda request: httpx.Response(
            status_code=200,
            json=activity_payload | activity_response | json.loads(request.content),
        ),
        url=f"http://my-url/{activity_route}/{activity_id}",
        method="PATCH",
    )
    test_module.handle_task_failure_callback(
        activity_id=activity_id,
        db_client=db_client,
        task_definition=TASK_DEFINITIONS[task_type],
    )


@pytest.mark.parametrize(
    ("task_type", "activity_route", "activity_response"),
    [
        (
            TaskType.circuit_extraction,
            "task-activity",
            {"task_activity_type": TaskActivityType.circuit_extraction__execution},
        ),
        (TaskType.circuit_simulation_neurodamus_cluster, "simulation-execution", {}),
    ],
)
def test_handle_task_failure_callback__do_nothing(
    db_client, task_type, activity_route, activity_response, httpx_mock
):
    activity_id = uuid4()

    activity_payload = {
        "id": str(activity_id),
        "status": "done",
        "start_time": datetime.now(UTC).isoformat(),
    }
    httpx_mock.add_response(
        url=f"http://my-url/{activity_route}/{activity_id}",
        method="GET",
        json=activity_payload | activity_response,
    )
    test_module.handle_task_failure_callback(
        activity_id=activity_id,
        db_client=db_client,
        task_definition=TASK_DEFINITIONS[task_type],
    )


def test_estimate_task_resources_passthrough(db_client):
    """Non-circuit_extraction tasks should return resources unchanged."""
    task_definition = TASK_DEFINITIONS[TaskType.morphology_skeletonization]
    json_model = TaskLaunchSubmit(
        task_type=TaskType.morphology_skeletonization,
        config_id=uuid4(),
    )

    result = test_module.estimate_task_resources(
        json_model=json_model,
        db_client=db_client,
        task_definition=task_definition,
        compute_cell="cell_b",
    )
    assert result == task_definition.resources.model_copy(update={"compute_cell": "cell_b"})


def test_estimate_task_resources_circuit_extraction(db_client):
    """Circuit extraction tasks should delegate to circuit_extraction.estimate_task_resources."""
    task_definition = TASK_DEFINITIONS[TaskType.circuit_extraction]
    json_model = TaskLaunchSubmit(task_type=TaskType.circuit_extraction, config_id=uuid4())
    expected = MachineResources(cores=4, memory=16, timelimit="02:00", compute_cell="local")

    with patch(
        "app.services.resource_estimation.circuit_extraction.estimate_task_resources",
        return_value=expected,
        autospec=True,
    ) as mock_estimate:
        result = test_module.estimate_task_resources(
            json_model=json_model,
            db_client=db_client,
            task_definition=task_definition,
            compute_cell="cell_b",
        )

    assert result is expected
    mock_estimate.assert_called_once_with(
        json_model=json_model,
        db_client=db_client,
        task_definition=task_definition,
        compute_cell="cell_b",
    )


def test_estimate_task_resources_circuit_simulation(db_client, config_id, httpx_mock):
    task_definition = TASK_DEFINITIONS[TaskType.circuit_simulation_neurodamus_cluster]

    circuit_id = uuid4()
    json_model = TaskLaunchSubmit(
        task_type=TaskType.circuit_simulation_neurodamus_cluster, config_id=config_id
    )
    mocked_instances = {
        "cell_a": [
            ClusterInstanceInfo(name="big", max_neurons=1_000_000, memory_per_instance_gb=100),
            ClusterInstanceInfo(name="small", max_neurons=100, memory_per_instance_gb=10),
        ]
    }

    httpx_mock.add_response(
        url=f"http://my-url/simulation/{config_id}",
        method="GET",
        json={
            "id": str(config_id),
            "entity_id": str(circuit_id),
            "simulation_campaign_id": str(uuid4()),
            "scan_parameters": {},
            "number_neurons": 1000,
        },
    )
    with patch.object(
        app.services.resource_estimation.circuit_simulation,
        "CLUSTER_INSTANCES_INFO",
        mocked_instances,
    ):
        result = test_module.estimate_task_resources(
            json_model=json_model,
            db_client=db_client,
            task_definition=task_definition,
            compute_cell="cell_a",
        )
    assert result.type == "cluster"
    assert result.instance_type == "big"
    assert result.instances == 1
    assert result.compute_cell == "cell_a"


@pytest.mark.parametrize(
    ("target_simulator_name", "circuit_scale", "expected_task"),
    [
        ("LearningEngine", "system", TaskType.circuit_simulation_inait_machine),
        ("NEURON", "small", TaskType.circuit_simulation_neuron),
        ("CORENEURON", "microcircuit", TaskType.circuit_simulation_neurodamus_cluster),
        ("Brian2", "small", TaskType.circuit_simulation_brian2_machine),
    ],
)
def test_select_simulation_task(
    target_simulator_name,
    circuit_scale,
    expected_task,
):
    db_client = Mock()
    config_id = uuid4()
    simulation_entity_id = uuid4()

    simulation = SimpleNamespace(entity_id=simulation_entity_id)
    circuit = SimpleNamespace(
        scale=circuit_scale,
        target_simulator=target_simulator_name,
    )
    db_client.get_entity.side_effect = [simulation, circuit]

    with (
        patch.object(test_module.db_sdk, "select_asset_content", return_value="config_json"),
        patch.object(
            test_module.libsonata,
            "SimulationConfig",
            return_value=SimpleNamespace(
                target_simulator=SimpleNamespace(name=target_simulator_name),
            ),
        ),
    ):
        task_type = test_module.select_simulation_task(
            db_client=db_client,
            config_id=config_id,
            config_type=entitysdk.models.Simulation,
        )

    assert task_type == expected_task


def test_select_simulation_task_falls_back_to_circuit_target_simulator():
    db_client = Mock()
    config_id = uuid4()
    simulation_entity_id = uuid4()

    simulation = SimpleNamespace(entity_id=simulation_entity_id)
    circuit = SimpleNamespace(
        scale="small",
        target_simulator="NEURON",
    )
    db_client.get_entity.side_effect = [simulation, circuit]

    unspecified = libsonata.SimulationConfig.SimulatorType.UNSPECIFIED

    with (
        patch.object(test_module.db_sdk, "select_asset_content", return_value="config_json"),
        patch.object(test_module.libsonata, "SimulationConfig") as mock_sim_config,
    ):
        mock_sim_config.return_value = SimpleNamespace(target_simulator=unspecified)
        mock_sim_config.SimulatorType.UNSPECIFIED = unspecified
        task_type = test_module.select_simulation_task(
            db_client=db_client,
            config_id=config_id,
            config_type=entitysdk.models.Simulation,
        )

    assert task_type == TaskType.circuit_simulation_neuron


def test_select_simulation_task_raises_for_unsupported_target_simulator():
    db_client = Mock()
    config_id = uuid4()
    simulation_entity_id = uuid4()

    simulation = SimpleNamespace(entity_id=simulation_entity_id)
    circuit = SimpleNamespace(
        scale="small",
        target_simulator="UNSUPPORTED",
    )
    db_client.get_entity.side_effect = [simulation, circuit]

    with (
        patch.object(test_module.db_sdk, "select_asset_content", return_value="config_json"),
        patch.object(
            test_module.libsonata,
            "SimulationConfig",
            return_value=SimpleNamespace(
                target_simulator=libsonata.SimulationConfig.SimulatorType.UNSPECIFIED
            ),
        ),
        pytest.raises(RuntimeError, match="Unsupported target simulator"),
    ):
        test_module.select_simulation_task(
            db_client=db_client,
            config_id=config_id,
            config_type=entitysdk.models.Simulation,
        )


def test_select_simulation_task_raises_api_error_for_invalid_config_format():
    db_client = Mock()
    config_id = uuid4()
    simulation = SimpleNamespace(id=config_id, entity_id=uuid4())
    db_client.get_entity.return_value = simulation
    sonata_error = test_module.libsonata.SonataError("invalid simulation config")

    with (
        patch.object(test_module.db_sdk, "select_asset_content", return_value="config_json"),
        patch.object(test_module.libsonata, "SimulationConfig", side_effect=sonata_error),
        pytest.raises(ApiError) as exc_info,
    ):
        test_module.select_simulation_task(
            db_client=db_client,
            config_id=config_id,
            config_type=entitysdk.models.Simulation,
        )

    assert exc_info.value.error_code == ApiErrorCode.INVALID_CONFIG_FORMAT
    assert exc_info.value.http_status_code == HTTPStatus.BAD_REQUEST
    assert exc_info.value.details == "invalid simulation config"
    assert str(config_id) in exc_info.value.message
