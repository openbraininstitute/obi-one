from types import SimpleNamespace
from unittest.mock import Mock, call, patch
from uuid import uuid4

import pytest
from entitysdk import models

from app.errors import ApiError, ApiErrorCode
from app.mappings import TASK_DEFINITIONS
from app.schemas.cluster import ClusterInstanceInfo
from app.schemas.task import TaskLaunchSubmit, TaskType
from app.services.resource_estimation import circuit_simulation as test_module


def _make_db_client(number_neurons: int) -> tuple[Mock, str]:
    circuit_id = str(uuid4())
    db_client = Mock()
    db_client.get_entity.side_effect = [
        SimpleNamespace(entity_id=circuit_id),
        SimpleNamespace(number_neurons=number_neurons),
    ]
    return db_client, circuit_id


def test_estimate_task_resources_success():
    json_model = TaskLaunchSubmit(task_type=TaskType.circuit_simulation, config_id=uuid4())
    task_definition = TASK_DEFINITIONS[TaskType.circuit_simulation_neurodamus_cluster]
    db_client, circuit_id = _make_db_client(number_neurons=9)
    mocked_instances = {
        "cell_a": [
            ClusterInstanceInfo(name="big", max_neurons=10, memory_per_instance_gb=100),
            ClusterInstanceInfo(name="small", max_neurons=8, memory_per_instance_gb=10),
        ]
    }

    with patch.object(
        test_module,
        "CLUSTER_INSTANCES_INFO",
        mocked_instances,
    ):
        result = test_module.estimate_task_resources(
            json_model=json_model,
            db_client=db_client,
            task_definition=task_definition,
            compute_cell="cell_a",
        )

    assert result.instances == 1
    assert result.instance_type == "big"
    assert result.compute_cell == "cell_a"
    db_client.get_entity.assert_has_calls(
        [
            call(entity_id=json_model.config_id, entity_type=models.Simulation),
            call(entity_id=circuit_id, entity_type=models.Circuit),
        ]
    )


def test_estimate_task_resources_unknown_compute_cell():
    json_model = TaskLaunchSubmit(task_type=TaskType.circuit_simulation, config_id=uuid4())
    task_definition = TASK_DEFINITIONS[TaskType.circuit_simulation]
    db_client, _ = _make_db_client(number_neurons=20_000)

    with pytest.raises(ApiError) as exc_info:
        test_module.estimate_task_resources(
            json_model=json_model,
            db_client=db_client,
            task_definition=task_definition,
            compute_cell="unknown_cell",
        )

    assert exc_info.value.error_code == ApiErrorCode.RESOURCE_ESTIMATION_ERROR


def test_estimate_task_resources_no_available_instances():
    json_model = TaskLaunchSubmit(task_type=TaskType.circuit_simulation, config_id=uuid4())
    task_definition = TASK_DEFINITIONS[TaskType.circuit_simulation]
    db_client, _ = _make_db_client(number_neurons=100)
    mocked_instances = {
        "cell_a": [
            ClusterInstanceInfo(name="big-only", max_neurons=10, memory_per_instance_gb=32),
        ]
    }

    with (
        patch.object(test_module, "CLUSTER_INSTANCES_INFO", mocked_instances),
        pytest.raises(ApiError) as exc_info,
    ):
        test_module.estimate_task_resources(
            json_model=json_model,
            db_client=db_client,
            task_definition=task_definition,
            compute_cell="cell_a",
        )

    assert exc_info.value.error_code == ApiErrorCode.RESOURCE_ESTIMATION_ERROR
