import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import entitysdk
import httpx
import pytest
from entitysdk.types import AssetLabel

from app.mappings import TASK_DEFINITIONS
from app.schemas.callback import CallBack, CallBackAction, CallBackEvent, HttpRequestCallBackConfig
from app.schemas.task import TaskLaunchSubmit, TaskType
from app.services import task as test_module
from obi_one.scientific.library.circuit_metrics import (
    CircuitMetricsEdgePopulation,
    CircuitMetricsNodePopulation,
    CircuitMetricsOutput,
    EdgePopulationType,
    NodePopulationType,
)

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
    ("task_type", "config_route", "config_response", "activity_route"),
    [
        (
            TaskType.circuit_extraction,
            "circuit-extraction-config",
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
            },
            "circuit-extraction-execution",
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
        ),
    ],
)
def test_submit_task_job__success(
    task_type,
    config_route,
    config_response,
    activity_route,
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
            json=json.loads(request.content) | {"id": str(activity_id)},
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
        compute_cell="cell_a",
    )
    assert res.task_type == task_type
    assert res.config_id == config_id
    assert res.activity_id == activity_id
    assert res.job_id == job_id


@pytest.mark.parametrize(
    ("task_type", "config_route", "config_response", "activity_route"),
    [
        (
            TaskType.circuit_extraction,
            "circuit-extraction-config",
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
            },
            "circuit-extraction-execution",
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
        ),
    ],
)
def test_submit_task_job__failure(
    task_type,
    config_route,
    config_response,
    activity_route,
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
            json=json.loads(request.content) | {"id": str(activity_id)},
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
            compute_cell="cell_a",
        )


def test_circuit_simulation_job_data(config_id, activity_id, callbacks):
    task_definition = TASK_DEFINITIONS["circuit_simulation"]

    res = test_module._circuit_simulation_job_data(
        simulation_id=config_id,
        simulation_execution_id=activity_id,
        project_id=PROJECT_ID,
        callbacks=callbacks,
        task_definition=task_definition,
        compute_cell="cell_a",
    )

    assert res == {
        "resources": {
            "type": "cluster",
            "instances": 1,
            "instance_type": "small",
            "timelimit": "00:10",
            "compute_cell": "cell_a",
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
        project_id=PROJECT_ID,
        virtual_lab_id=VIRTUAL_LAB_ID,
        task_definition=task_definition,
        entity_cache=True,
        output_root="/foo",
        callbacks=callbacks,
        compute_cell="cell_b",
    )

    assert res == {
        "resources": {
            "type": "machine",
            "cores": 1,
            "memory": 2,
            "timelimit": "00:10",
            "compute_cell": "cell_b",
        },
        "code": {
            "type": "python_repository",
            "location": "https://github.com/openbraininstitute/obi-one.git",
            "ref": task_definition.code.ref,
            "path": "launch_scripts/launch_task_for_single_config_asset/code.py",
            "dependencies": (
                "launch_scripts/launch_task_for_single_config_asset/dependencies/default.txt"
            ),
            "capabilities": {
                "private_packages": False,
            },
        },
        "inputs": [
            "--task-type circuit_extraction",
            "--config_entity_type CircuitExtractionConfig",
            f"--config_entity_id {config_id}",
            "--entity_cache True",
            "--scan_output_root /foo",
            f"--virtual_lab_id {VIRTUAL_LAB_ID}",
            f"--project_id {PROJECT_ID}",
            "--execution_activity_type CircuitExtractionExecution",
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
    ("task_type", "activity_route"),
    [
        (TaskType.circuit_extraction, "circuit-extraction-execution"),
        (TaskType.circuit_simulation, "simulation-execution"),
    ],
)
def test_handle_task_failure_callback(db_client, task_type, activity_route, httpx_mock):
    activity_id = uuid4()
    activity_payload = {
        "id": str(activity_id),
        "status": "running",
        "start_time": datetime.now(UTC).isoformat(),
    }
    httpx_mock.add_response(
        url=f"http://my-url/{activity_route}/{activity_id}",
        method="GET",
        json=activity_payload,
    )
    httpx_mock.add_callback(
        lambda request: httpx.Response(
            status_code=200,
            json=activity_payload | json.loads(request.content),
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
    ("task_type", "activity_route"),
    [
        (TaskType.circuit_extraction, "circuit-extraction-execution"),
        (TaskType.circuit_simulation, "simulation-execution"),
    ],
)
def test_handle_task_failure_callback__do_nothing(db_client, task_type, activity_route, httpx_mock):
    activity_id = uuid4()

    activity_payload = {
        "id": str(activity_id),
        "status": "done",
        "start_time": datetime.now(UTC).isoformat(),
    }
    httpx_mock.add_response(
        url=f"http://my-url/{activity_route}/{activity_id}",
        method="GET",
        json=activity_payload,
    )
    test_module.handle_task_failure_callback(
        activity_id=activity_id,
        db_client=db_client,
        task_definition=TASK_DEFINITIONS[task_type],
    )


@pytest.mark.parametrize(
    ("mem_required", "expected"),
    [
        (1, (1, 2)),
        (3, (1, 4)),
        (7, (1, 8)),
        (10, (2, 12)),
        (50, (8, 60)),
        (100, (16, 120)),
    ],
)
def test_get_required_cpu_memory_combo(mem_required, expected):
    assert test_module._get_required_cpu_memory_combo(mem_required) == expected


def test_get_required_cpu_memory_combo_too_large():
    with pytest.raises(ValueError, match="No CPU/memory combination found"):
        test_module._get_required_cpu_memory_combo(200)


def test_check_available_disk_space_ok():
    test_module._check_available_disk_space(10.0)


def test_check_available_disk_space_too_large():
    with pytest.raises(ValueError, match="Not enough disk space"):
        test_module._check_available_disk_space(25.0)


def _make_circuit_metrics(nbio_nodes, nvirt_nodes, sbio_edges, svirt_edges):
    """Helper to build a CircuitMetricsOutput with given node/edge counts."""
    return CircuitMetricsOutput(
        number_of_biophys_node_populations=1,
        number_of_virtual_node_populations=1,
        names_of_biophys_node_populations=["bio_pop"],
        names_of_virtual_node_populations=["virt_pop"],
        names_of_nodesets=[],
        biophysical_node_populations=[
            CircuitMetricsNodePopulation(
                number_of_nodes=nbio_nodes,
                name="bio_pop",
                population_type=NodePopulationType.biophysical,
                property_names=[],
                property_unique_values={},
                property_value_counts={},
                node_location_info=None,
            ),
        ],
        virtual_node_populations=[
            CircuitMetricsNodePopulation(
                number_of_nodes=nvirt_nodes,
                name="virt_pop",
                population_type=NodePopulationType.virtual,
                property_names=[],
                property_unique_values={},
                property_value_counts={},
                node_location_info=None,
            ),
        ],
        number_of_chemical_edge_populations=2,
        number_of_electrical_edge_populations=0,
        names_of_chemical_edge_populations=["bio_edges", "virt_edges"],
        names_of_electrical_edge_populations=[],
        chemical_edge_populations=[
            CircuitMetricsEdgePopulation(
                number_of_edges=sbio_edges,
                name="bio_edges",
                population_type=EdgePopulationType.chemical,
                source_name="bio_pop",
                target_name="bio_pop",
                property_names=[],
                property_stats=None,
                degree_stats=None,
            ),
            CircuitMetricsEdgePopulation(
                number_of_edges=svirt_edges,
                name="virt_edges",
                population_type=EdgePopulationType.chemical,
                source_name="virt_pop",
                target_name="bio_pop",
                property_names=[],
                property_stats=None,
                degree_stats=None,
            ),
        ],
        electrical_edge_populations=[],
    )


def _run_update_resources(db_client, circuit_metrics, do_virtual):
    """Run update_resources for circuit_extraction with mocked dependencies."""
    task_definition = TASK_DEFINITIONS[TaskType.circuit_extraction]
    json_model = TaskLaunchSubmit(task_type=TaskType.circuit_extraction, config_id=uuid4())
    fake_config = SimpleNamespace(initialize=SimpleNamespace(do_virtual=do_virtual))
    fake_entity = SimpleNamespace(circuit_id=uuid4())

    with (
        patch.object(db_client, "get_entity", return_value=fake_entity),
        patch.object(db_client, "download_content", return_value=b'{"type": "Fake"}'),
        patch(
            "app.services.task.get_circuit_metrics",
            return_value=circuit_metrics,
        ),
        patch(
            "app.services.task.deserialize_obi_object_from_json_data",
            return_value=fake_config,
        ),
        patch("app.services.task.db_sdk.get_config_asset") as mock_get_asset,
    ):
        mock_get_asset.return_value = SimpleNamespace(id=uuid4())
        return test_module.update_resources(
            json_model=json_model,
            db_client=db_client,
            task_definition=task_definition,
        )


# Formulas in update_resources:
#   input_neurons = (nbio + nvirt) if do_virtual else nbio
#   mem_gb_required = 1 + 55e-6 * input_neurons
#   time_h = ceil(input_neurons * 5e-6)
#   input_synapses = (sbio + svirt) if do_virtual else sbio
#   disk_gb = 1 + input_synapses * 1.85e-7


@pytest.mark.parametrize(
    ("nbio", "nvirt", "sbio", "svirt", "do_virtual", "exp_cores", "exp_mem", "exp_time"),
    [
        # Small circuit: 1000 bio + 500 virt, do_virtual=True
        #   neurons=1500, mem=1.0825 -> (1,2), time=ceil(0.0075)=1
        (1000, 500, 50_000, 20_000, True, 1, 2, "01:00"),
        # Small circuit: 1000 bio, do_virtual=False (virtual nodes ignored)
        #   neurons=1000, mem=1.055 -> (1,2), time=ceil(0.005)=1
        (1000, 500, 50_000, 20_000, False, 1, 2, "01:00"),
        # Medium circuit: 100k bio + 50k virt, do_virtual=True
        #   neurons=150000, mem=9.25 -> (2,12), time=ceil(0.75)=1
        (100_000, 50_000, 1_000_000, 500_000, True, 2, 12, "01:00"),
        # Medium circuit: 100k bio, do_virtual=False
        #   neurons=100000, mem=6.5 -> (1,8), time=ceil(0.5)=1
        (100_000, 50_000, 1_000_000, 500_000, False, 1, 8, "01:00"),
        # Large circuit: 500k bio + 200k virt, do_virtual=True
        #   neurons=700000, mem=39.5 -> (8,48), time=ceil(3.5)=4
        (500_000, 200_000, 10_000_000, 5_000_000, True, 8, 48, "04:00"),
        # Large circuit: 500k bio, do_virtual=False
        #   neurons=500000, mem=28.5 -> (4,30), time=ceil(2.5)=3
        (500_000, 200_000, 10_000_000, 5_000_000, False, 4, 30, "03:00"),
    ],
    ids=[
        "small_with_virtual",
        "small_without_virtual",
        "medium_with_virtual",
        "medium_without_virtual",
        "large_with_virtual",
        "large_without_virtual",
    ],
)
def test_update_resources_allocation(
    db_client, nbio, nvirt, sbio, svirt, do_virtual, exp_cores, exp_mem, exp_time
):
    metrics = _make_circuit_metrics(nbio, nvirt, sbio, svirt)
    result = _run_update_resources(db_client, metrics, do_virtual)

    assert result.resources.cores == exp_cores
    assert result.resources.memory == exp_mem
    assert result.resources.timelimit == exp_time


@pytest.mark.parametrize(
    ("sbio", "svirt", "do_virtual"),
    [
        # do_virtual=True: total = 60M + 50M = 110M synapses
        #   disk = 1 + 110e6 * 1.85e-7 = 21.35 GB > 20 GB limit
        (60_000_000, 50_000_000, True),
        # do_virtual=False: only bio = 110M synapses
        #   disk = 1 + 110e6 * 1.85e-7 = 21.35 GB > 20 GB limit
        (110_000_000, 50_000_000, False),
    ],
    ids=["too_many_synapses_with_virtual", "too_many_synapses_without_virtual"],
)
def test_update_resources_disk_space_limit(db_client, sbio, svirt, do_virtual):
    metrics = _make_circuit_metrics(1000, 500, sbio, svirt)
    with pytest.raises(ValueError, match="Not enough disk space"):
        _run_update_resources(db_client, metrics, do_virtual)


@pytest.mark.parametrize(
    ("sbio", "svirt", "do_virtual"),
    [
        # do_virtual=False: only bio = 60M, disk = 1 + 60e6*1.85e-7 = 12.1 GB < 20
        (60_000_000, 50_000_000, False),
    ],
    ids=["under_limit_without_virtual"],
)
def test_update_resources_disk_ok_without_virtual(db_client, sbio, svirt, do_virtual):
    """With do_virtual=False, virtual synapses are excluded and disk check passes."""
    metrics = _make_circuit_metrics(1000, 500, sbio, svirt)
    result = _run_update_resources(db_client, metrics, do_virtual)
    assert result.resources.cores >= 1


def test_update_resources_passthrough(db_client):
    """Non-circuit_extraction tasks should return task_definition unchanged."""
    task_definition = TASK_DEFINITIONS[TaskType.circuit_simulation]
    json_model = TaskLaunchSubmit(task_type=TaskType.circuit_simulation, config_id=uuid4())

    result = test_module.update_resources(
        json_model=json_model,
        db_client=db_client,
        task_definition=task_definition,
    )
    assert result is task_definition
