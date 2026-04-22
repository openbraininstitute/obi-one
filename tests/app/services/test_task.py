import json
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import UUID, uuid4

import entitysdk
import httpx
import pytest
from entitysdk.types import AssetLabel, TaskActivityType, TaskConfigType

import app.services.resource_estimation.circuit_simulation
from app.mappings import TASK_DEFINITIONS
from app.schemas.callback import CallBack, CallBackAction, CallBackEvent, HttpRequestCallBackConfig
from app.schemas.cluster import ClusterInstanceInfo
from app.schemas.task import MachineResources, TaskLaunchSubmit, TaskType
from app.services import task as test_module

from tests.utils import PROJECT_ID, VIRTUAL_LAB_ID

ASSET_ID = uuid4()


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
            "task_type": TaskType.circuit_simulation,
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
            TaskType.circuit_simulation,
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
            TaskType.circuit_simulation,
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


def test_circuit_simulation_job_data(config_id, activity_id, callbacks):
    task_definition = TASK_DEFINITIONS["circuit_simulation"]

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
                        "task_type": "circuit_simulation",
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
                        "task_type": "circuit_simulation",
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
        (TaskType.circuit_simulation, "simulation-execution", {}),
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
        (TaskType.circuit_simulation, "simulation-execution", {}),
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
    task_definition = TASK_DEFINITIONS[TaskType.circuit_simulation]

    circuit_id = uuid4()
    json_model = TaskLaunchSubmit(task_type=TaskType.circuit_simulation, config_id=config_id)
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
        },
    )
    httpx_mock.add_response(
        url=f"http://my-url/circuit/{circuit_id}",
        method="GET",
        json={
            "id": str(circuit_id),
            "number_neurons": 1000,
            "number_connections": 20,
            "number_synapses": 35,
            "scale": "microcircuit",
            "build_category": "em_reconstruction",
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
