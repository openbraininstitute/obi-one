import math
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
    db_client = Mock()
    db_client.get_entity.return_value = SimpleNamespace(number_neurons=number_neurons)
    return db_client


def test_estimate_task_resources_success():
    json_model = TaskLaunchSubmit(task_type=TaskType.circuit_simulation, config_id=uuid4())
    task_definition = TASK_DEFINITIONS[TaskType.circuit_simulation_neurodamus_cluster]
    db_client = _make_db_client(number_neurons=9)
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
        ]
    )


def test_estimate_task_resources_scales_instances_with_mem_per_cell():
    """Mem estimate should request enough nodes for MEM_GB_PER_CELL * neurons."""
    number_neurons = 5_000
    memory_per_instance_gb = 100
    json_model = TaskLaunchSubmit(task_type=TaskType.circuit_simulation, config_id=uuid4())
    task_definition = TASK_DEFINITIONS[TaskType.circuit_simulation_neurodamus_cluster]
    db_client = _make_db_client(number_neurons=number_neurons)
    mocked_instances = {
        "cell_a": [
            ClusterInstanceInfo(
                name="big",
                max_neurons=number_neurons,
                memory_per_instance_gb=memory_per_instance_gb,
            ),
        ]
    }
    expected_instances = math.ceil(
        test_module.MEM_GB_PER_CELL * number_neurons / memory_per_instance_gb
    )

    with patch.object(test_module, "CLUSTER_INSTANCES_INFO", mocked_instances):
        result = test_module.estimate_task_resources(
            json_model=json_model,
            db_client=db_client,
            task_definition=task_definition,
            compute_cell="cell_a",
        )

    # 5000 * 0.09 GB/cell / 100 GB/node => 5 nodes (temporary CA3 Mem(GB)/cell bump).
    assert expected_instances == 5
    assert result.instances == expected_instances
    assert result.instance_type == "big"


def test_estimate_task_resources_unknown_compute_cell():
    json_model = TaskLaunchSubmit(task_type=TaskType.circuit_simulation, config_id=uuid4())
    task_definition = TASK_DEFINITIONS[TaskType.circuit_simulation]
    db_client = _make_db_client(number_neurons=20_000)

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
    db_client = _make_db_client(number_neurons=100)
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
