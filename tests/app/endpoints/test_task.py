import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from entitysdk.types import CircuitScale, TargetSimulator
from obp_accounting_sdk.constants import ServiceSubtype

from app.application import app
from app.config import settings
from app.dependencies.compute_cell import get_compute_cell
from app.mappings import APP_TAG, OBI_ONE_CODE_PATH, OBI_ONE_DEPS_DIR, TASK_DEFINITIONS
from app.schemas.accounting import AccountingParameters
from app.schemas.callback import CallBack, CallBackAction, CallBackEvent, HttpRequestCallBackConfig
from app.schemas.task import TaskAccountingInfo, TaskLaunchInfo
from app.services.accounting import CIRCUIT_SCALE_TO_SERVICE_SUBTYPE
from app.types import TaskType

from tests.utils import PROJECT_ID, VIRTUAL_LAB_ID, assert_request


@pytest.fixture
def callbacks():
    config = HttpRequestCallBackConfig(
        url="http://failure",
        method="POST",
    )
    return [
        CallBack(
            event_type=CallBackEvent.job_on_failure,
            action_type=CallBackAction.http_request_with_token,
            config=config,
        )
    ]


@pytest.mark.parametrize(
    "task_type",
    [
        TaskType.circuit_extraction,
        TaskType.circuit_simulation_inait_machine,
        TaskType.circuit_simulation_neuron,
        TaskType.circuit_simulation_neurodamus_cluster,
        TaskType.morphology_skeletonization,
        TaskType.ion_channel_model_simulation_execution,
        TaskType.em_synapse_mapping,
    ],
)
def test_task_launch_success(
    client,
    callbacks,
    task_type,
    monkeypatch,
):
    task_definition = TASK_DEFINITIONS[task_type]

    job_id = uuid4()
    config_id = uuid4()
    activity_id = uuid4()
    accounting_session = SimpleNamespace(job_id="job-123", finish=Mock())
    accounting_parameters = AccountingParameters(
        count=10,
        service_subtype=ServiceSubtype.SMALL_SIM,
    )
    task_accounting_info = TaskAccountingInfo(
        cost=123.4,
        config_id=config_id,
        parameters=accounting_parameters,
        task_type=task_type,
    )
    task_launch_info = TaskLaunchInfo(
        job_id=job_id,
        config_id=config_id,
        task_type=task_type,
        activity_id=activity_id,
    )
    monkeypatch.setitem(
        app.dependency_overrides,
        get_compute_cell,
        lambda: "cell_a",
    )
    with (
        patch(
            "app.services.accounting.estimate_task_cost",
            return_value=task_accounting_info,
            autospec=True,
        ),
        patch(
            "app.services.accounting.make_task_reservation",
            return_value=accounting_session,
            autospec=True,
        ),
        patch(
            "app.services.accounting.generate_accounting_callbacks",
            return_value=callbacks,
            autospec=True,
        ),
        patch(
            "app.services.task.estimate_task_resources",
            return_value=task_definition.resources,
            autospec=True,
        ),
        patch(
            "app.services.task.submit_task_job",
            return_value=task_launch_info,
            autospec=True,
        ) as patched_task_job,
    ):
        data = (
            client.post(
                url="/declared/task/launch",
                json={
                    "task_type": task_type,
                    "config_id": str(config_id),
                },
            )
            .raise_for_status()
            .json()
        )

        assert data["job_id"] == str(job_id)
        assert data["config_id"] == str(config_id)
        assert data["activity_id"] == str(activity_id)
        assert data["task_type"] == task_type

        patched_task_job.side_effect = RuntimeError("submit failed")

        resp = client.post(
            url="/declared/task/launch",
            json={
                "task_type": task_type,
                "config_id": str(config_id),
            },
        )
        assert resp.status_code == 500

        accounting_session.finish.assert_called_once_with(exc_type=RuntimeError)


def _simulation_config(target_simulator: str):
    return {
        "manifest": {"$OUTPUT_DIR": "./reporting", "$INPUT_DIR": "./"},
        "run": {"tstop": 1000.0, "dt": 0.01, "spike_threshold": -15, "random_seed": 42},
        "target_simulator": target_simulator,
        "network": "$INPUT_DIR/circuit_config.json",
        "conditions": {"celsius": 34.0, "v_init": -80, "other": "something"},
        "node_sets_file": "$INPUT_DIR/node_sets_simple.json",
        "mechanisms_dir": "../shared_components_mechanisms",
        "inputs": {
            "current_clamp_1": {
                "input_type": "current_clamp",
                "module": "linear",
                "node_set": "Layer23",
                "amp_start": 190.0,
                "delay": 100.0,
                "duration": 800.0,
            },
            "spikes_1": {
                "input_type": "spikes",
                "module": "synapse_replay",
                "delay": 800,
                "duration": 100,
                "node_set": "Layer23",
                "source": "Layer23",
                "spike_file": "input_spikes.h5",
            },
        },
        "output": {
            "output_dir": "$OUTPUT_DIR",
            "log_file": "log_spikes.log",
            "spikes_file": "spikes.h5",
            "spikes_sort_order": "by_time",
        },
        "reports": {},
    }


def _simulation_metadata(*, simulation_id, circuit_id, config_id):
    return {
        "id": str(simulation_id),
        "name": "sim",
        "simulation_campaign_id": str(uuid4()),
        "entity_id": str(circuit_id),
        "scan_parameters": {},
        "number_neurons": 100,
        "assets": [
            {
                "id": str(config_id),
                "path": "simulation_config.json",
                "full_path": "/simulation_config.json",
                "entity_id": str(simulation_id),
                "sha256_digest": None,
                "created_by_id": str(uuid4()),
                "updated_by_id": str(uuid4()),
                "label": "sonata_simulation_config",
                "storage_type": "aws_s3_internal",
                "is_directory": False,
                "content_type": "application/json",
                "size": 0,
            }
        ],
    }


def _circuit_config():
    return {
        "manifest": {"$BASE_DIR": ".", "$COMPONENT_DIR": "$BASE_DIR", "$NETWORK_DIR": "./"},
        "target_simulator": "NEURON",
        "components": {
            "biophysical_neuron_models_dir": "$COMPONENT_DIR/biophysical_neuron_models",
            "morphologies_dir": "$COMPONENT_DIR/morphologies",
        },
        "node_sets_file": "$BASE_DIR/node_sets.json",
        "networks": {
            "nodes": [
                {
                    "nodes_file": "$NETWORK_DIR/nodes.h5",
                    "populations": {
                        "default": {"type": "biophysical"},
                        "default2": {
                            "type": "biophysical",
                            "spatial_segment_index_dir": "path/to/node/dir",
                        },
                    },
                }
            ],
            "edges": [],
        },
    }


def _circuit_metadata(*, circuit_id: UUID, target_simulator: str, circuit_scale: str):
    return {
        "id": str(circuit_id),
        "name": "circuit",
        "number_neurons": 1000,
        "number_synapses": 1_000_000_000,
        "number_connections": 100_000_000,
        "has_morphologies": True,
        "has_point_neurons": True,
        "has_spines": True,
        "has_electrical_cell_models": True,
        "root_circuit_id": None,
        "atlas_id": str(uuid4()),
        "subject_id": str(uuid4()),
        "build_category": "em_reconstruction",
        "authorized_project_id": PROJECT_ID,
        "authorized_public": True,
        "created_by_id": str(uuid4()),
        "updated_by_id": str(uuid4()),
        "brain_region_id": str(uuid4()),
        "license_id": str(uuid4()),
        "target_simulator": target_simulator,
        "scale": circuit_scale,
        "assets": [],
    }


@pytest.mark.parametrize(
    "target_simulator",
    [TargetSimulator.NEURON, TargetSimulator.CORENEURON, TargetSimulator.LearningEngine],
)
@pytest.mark.parametrize(
    "circuit_scale",
    [
        CircuitScale.small,
        CircuitScale.microcircuit,
        CircuitScale.region,
        CircuitScale.system,
        CircuitScale.whole_brain,
    ],
)
def test_task_launch_success__circuit_simulation(
    client,
    httpx_mock,
    target_simulator,
    circuit_scale,
):
    circuit_id = uuid4()
    simulation_id = uuid4()
    simulation_config_asset_id = uuid4()
    simulation_execution_id = uuid4()
    db_url = settings.ENTITYCORE_URL
    job_id = uuid4()

    # mock response from vlab manager for determining the compute_cell
    httpx_mock.add_response(
        url=settings.get_virtual_lab_url(VIRTUAL_LAB_ID),
        method="GET",
        json={"data": {"virtual_lab": {"compute_cell": "cell_a"}}},
    )
    # mock simulation metadata response fetched to toggle between simulation task types
    httpx_mock.add_response(
        url=f"{db_url}/simulation/{simulation_id}",
        method="GET",
        json=_simulation_metadata(
            simulation_id=simulation_id, circuit_id=circuit_id, config_id=simulation_config_asset_id
        ),
        is_reusable=True,  # TODO: Refactor code to avoid multiple requests
    )
    # mock simulation config asset response used to access target_simulator from config
    httpx_mock.add_response(
        url=f"{db_url}/simulation/{simulation_id}/assets/{simulation_config_asset_id}/download",
        method="GET",
        json=_simulation_config(target_simulator=target_simulator),
    )
    # mock circuit metadata needed for fetching target_simulator/scale for toggling
    httpx_mock.add_response(
        url=f"{db_url}/circuit/{circuit_id}",
        method="GET",
        json=_circuit_metadata(
            circuit_id=circuit_id, target_simulator=target_simulator, circuit_scale=circuit_scale
        ),
        is_reusable=True,  # TODO: Refactor code to avoid multiple requests
    )
    httpx_mock.add_response(
        url=f"{settings.ACCOUNTING_BASE_URL}/estimate/oneshot",
        method="POST",
        json={"data": {"cost": 1000}},
    )
    httpx_mock.add_response(
        url=f"{settings.ACCOUNTING_BASE_URL}/reservation/oneshot",
        method="POST",
        json={"data": {"job_id": str(job_id), "amount": 200.0}},
    )
    httpx_mock.add_callback(
        lambda request: httpx.Response(
            status_code=200,
            json=json.loads(request.content) | {"id": str(simulation_execution_id)},
        ),
        url=f"{db_url}/simulation-execution",
        method="POST",
    )
    # mock the call to the launch-system for launching the job
    httpx_mock.add_response(
        url=f"{settings.LAUNCH_SYSTEM_URL}/job",
        method="POST",
        json={"id": str(job_id)},
    )
    # when task is launched activity is updated
    httpx_mock.add_callback(
        lambda request: httpx.Response(
            status_code=200,
            json={
                "id": str(simulation_execution_id),
                "start_time": datetime.now(UTC).isoformat(),
            }
            | json.loads(request.content),
        ),
        url=f"{db_url}/simulation-execution/{simulation_execution_id}",
        method="PATCH",
    )

    data = assert_request(
        client.post,
        url="/declared/task/launch",
        json={
            "task_type": TaskType.circuit_simulation,
            "config_id": str(simulation_id),
        },
    ).json()

    expected_task_type = {
        (TargetSimulator.NEURON, CircuitScale.small): TaskType.circuit_simulation_neuron,
        (
            TargetSimulator.NEURON,
            CircuitScale.microcircuit,
        ): TaskType.circuit_simulation_neurodamus_cluster,
        (
            TargetSimulator.NEURON,
            CircuitScale.region,
        ): TaskType.circuit_simulation_neurodamus_cluster,
        (
            TargetSimulator.NEURON,
            CircuitScale.system,
        ): TaskType.circuit_simulation_neurodamus_cluster,
        (
            TargetSimulator.NEURON,
            CircuitScale.whole_brain,
        ): TaskType.circuit_simulation_neurodamus_cluster,
        (TargetSimulator.CORENEURON, CircuitScale.small): TaskType.circuit_simulation_neuron,
        (
            TargetSimulator.CORENEURON,
            CircuitScale.microcircuit,
        ): TaskType.circuit_simulation_neurodamus_cluster,
        (
            TargetSimulator.CORENEURON,
            CircuitScale.region,
        ): TaskType.circuit_simulation_neurodamus_cluster,
        (
            TargetSimulator.CORENEURON,
            CircuitScale.system,
        ): TaskType.circuit_simulation_neurodamus_cluster,
        (
            TargetSimulator.CORENEURON,
            CircuitScale.whole_brain,
        ): TaskType.circuit_simulation_neurodamus_cluster,
        (
            TargetSimulator.LearningEngine,
            CircuitScale.small,
        ): TaskType.circuit_simulation_inait_machine,
        (
            TargetSimulator.LearningEngine,
            CircuitScale.microcircuit,
        ): TaskType.circuit_simulation_inait_machine,
        (
            TargetSimulator.LearningEngine,
            CircuitScale.region,
        ): TaskType.circuit_simulation_inait_machine,
        (
            TargetSimulator.LearningEngine,
            CircuitScale.system,
        ): TaskType.circuit_simulation_inait_machine,
        (
            TargetSimulator.LearningEngine,
            CircuitScale.whole_brain,
        ): TaskType.circuit_simulation_inait_machine,
    }[target_simulator, circuit_scale]

    response_task_type = data["task_type"]
    task_def = TASK_DEFINITIONS[response_task_type]

    assert response_task_type == expected_task_type

    job_request = httpx_mock.get_request(
        url=f"{settings.LAUNCH_SYSTEM_URL}/job",
        method="POST",
    )
    job_payload = json.loads(job_request.content)

    cluster_callbacks = [
        {
            "action_type": "http_request_with_token",
            "event_type": "job_on_failure",
            "config": {
                "url": f"{settings.API_URL}/declared/task/callback/failure",
                "method": "POST",
                "params": {
                    "task_type": response_task_type,
                    "activity_id": str(simulation_execution_id),
                },
                "headers": {
                    "virtual-lab-id": VIRTUAL_LAB_ID,
                    "project-id": PROJECT_ID,
                },
                "payload": None,
            },
        },
        {
            "action_type": "http_request_with_token",
            "event_type": "job_on_failure",
            "config": {
                "url": f"{settings.ACCOUNTING_BASE_URL}/reservation/oneshot/{job_id}",
                "method": "DELETE",
                "params": None,
                "headers": None,
                "payload": None,
            },
        },
        {
            "action_type": "http_request_with_token",
            "event_type": "job_on_success",
            "config": {
                "url": f"{settings.API_URL}/declared/task/callback/success",
                "method": "POST",
                "params": None,
                "headers": {
                    "virtual-lab-id": VIRTUAL_LAB_ID,
                    "project-id": PROJECT_ID,
                },
                "payload": {
                    "task_type": response_task_type,
                    "job_id": str(job_id),
                    "accounting_service_subtype": str(
                        CIRCUIT_SCALE_TO_SERVICE_SUBTYPE[circuit_scale]
                    ),
                    "count": 100,
                },
            },
        },
    ]

    generic_callbacks = [
        {
            "action_type": "http_request_with_token",
            "event_type": "job_on_failure",
            "config": {
                "url": f"{settings.API_URL}/declared/task/callback/failure",
                "method": "POST",
                "params": {
                    "task_type": response_task_type,
                    "activity_id": str(simulation_execution_id),
                },
                "headers": {
                    "virtual-lab-id": VIRTUAL_LAB_ID,
                    "project-id": PROJECT_ID,
                },
                "payload": None,
            },
        },
        {
            "action_type": "http_request_with_token",
            "event_type": "job_on_failure",
            "config": {
                "url": f"{settings.ACCOUNTING_BASE_URL}/reservation/oneshot/{job_id}",
                "method": "DELETE",
                "params": None,
                "headers": None,
                "payload": None,
            },
        },
        {
            "action_type": "http_request_with_token",
            "event_type": "job_on_success",
            "config": {
                "url": f"{settings.API_URL}/declared/task/callback/success",
                "method": "POST",
                "params": None,
                "headers": {
                    "virtual-lab-id": VIRTUAL_LAB_ID,
                    "project-id": PROJECT_ID,
                },
                "payload": {
                    "task_type": response_task_type,
                    "job_id": str(job_id),
                    "accounting_service_subtype": str(
                        CIRCUIT_SCALE_TO_SERVICE_SUBTYPE[circuit_scale]
                    ),
                    "count": 100,
                },
            },
        },
    ]
    match response_task_type:
        case TaskType.circuit_simulation_inait_machine:
            assert job_payload == {
                "code": task_def.code.model_dump(mode="json"),
                "resources": task_def.resources.model_dump(mode="json")
                | {"compute_cell": "cell_a"},
                "inputs": [
                    "sonata-simulation-task",
                    f" --project-id {PROJECT_ID}",
                    f" --virtual-lab-id {VIRTUAL_LAB_ID}",
                    f" --simulation-id {simulation_id}",
                    f" --simulation-execution-id {simulation_execution_id}",
                ],
                "project_id": PROJECT_ID,
                "callbacks": generic_callbacks,
            }

        case TaskType.circuit_simulation_neurodamus_cluster:
            assert job_payload == {
                "code": task_def.code.model_dump(mode="json"),
                "resources": {
                    "type": "cluster",
                    "instances": 1,
                    "instance_type": "large",
                    "compute_cell": "cell_a",
                    "timelimit": None,
                },
                "inputs": [
                    "--simulation-id",
                    str(simulation_id),
                    "--simulation-execution-id",
                    str(simulation_execution_id),
                ],
                "project_id": PROJECT_ID,
                "callbacks": cluster_callbacks,
            }

        case _:
            assert job_payload == {
                "code": {
                    "type": "python_repository",
                    "location": "https://github.com/openbraininstitute/obi-one.git",
                    "ref": APP_TAG,
                    "path": OBI_ONE_CODE_PATH,
                    "dependencies": str(OBI_ONE_DEPS_DIR / "default.txt"),
                    "capabilities": {"private_packages": False, "env_secrets": []},
                    "staged_directories": [],
                },
                "resources": task_def.resources.model_dump(mode="json")
                | {"compute_cell": "cell_a"},
                "inputs": [
                    "--task-type circuit_simulation_neuron",
                    "--config_entity_type Simulation",
                    f"--config_entity_id {simulation_id}",
                    "--entity_cache True",
                    "--scan_output_root ./obi-output",
                    f"--virtual_lab_id {VIRTUAL_LAB_ID}",
                    f"--project_id {PROJECT_ID}",
                    "--execution_activity_type SimulationExecution",
                    f"--execution_activity_id {simulation_execution_id}",
                ],
                "project_id": PROJECT_ID,
                "callbacks": generic_callbacks,
            }


@pytest.mark.parametrize(
    "task_type",
    [
        TaskType.circuit_extraction,
        TaskType.circuit_simulation_inait_machine,
        TaskType.circuit_simulation_neuron,
        TaskType.circuit_simulation_neurodamus_cluster,
        TaskType.morphology_skeletonization,
        TaskType.ion_channel_model_simulation_execution,
        TaskType.em_synapse_mapping,
    ],
)
def test_task_estimate(client, task_type):
    config_id = uuid4()

    accounting_parameters = AccountingParameters(
        count=10,
        service_subtype=ServiceSubtype.SMALL_SIM,
    )
    task_accounting_info = TaskAccountingInfo(
        cost=123.4,
        config_id=config_id,
        parameters=accounting_parameters,
        task_type=task_type,
    )
    with patch(
        "app.services.accounting.estimate_task_cost",
        return_value=task_accounting_info,
        autospec=True,
    ):
        data = (
            client.post(
                url="/declared/task/estimate",
                json={
                    "task_type": task_type,
                    "config_id": str(config_id),
                },
            )
            .raise_for_status()
            .json()
        )

    assert data["task_type"] == task_type
    assert data["config_id"] == str(config_id)
    assert data["cost"] == 123.4
    assert data["parameters"]["service_subtype"] == ServiceSubtype.SMALL_SIM
    assert data["parameters"]["count"] == 10


@pytest.mark.parametrize("task_type", TaskType)
def test_task_failure_endpoint(client, task_type):
    activity_id = uuid4()

    with patch("app.services.task.handle_task_failure_callback", autospec=True):
        client.post(
            url="/declared/task/callback/failure",
            params={
                "task_type": task_type,
                "activity_id": str(activity_id),
            },
        ).raise_for_status()


@pytest.mark.parametrize("task_type", TaskType)
def test_task_success_endpoint(client, task_type):
    job_id = uuid4()

    with patch("app.services.accounting.finish_accounting_session", autospec=True):
        client.post(
            url="/declared/task/callback/success",
            json={
                "task_type": task_type,
                "job_id": str(job_id),
                "accounting_service_subtype": ServiceSubtype.SMALL_SIM,
                "count": 11,
            },
        ).raise_for_status()
