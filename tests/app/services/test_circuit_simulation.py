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


# The failed job 01a1cb34: 9,587 cells and 219.1M synapses under CoreNEURON, on nodes of 788 GB.
FAILED_JOB = {"number_neurons": 9_587, "number_synapses": 219_100_000}
LARGE = {
    "cell_b": [ClusterInstanceInfo(name="large", max_neurons=10**6, memory_per_instance_gb=788)]
}


def _estimate_counted(simulation, *, simulator="CORENEURON"):
    db_client = Mock()
    db_client.get_entity.return_value = SimpleNamespace(**simulation)
    with (
        patch.object(test_module, "CLUSTER_INSTANCES_INFO", LARGE),
        patch.object(
            test_module.db_sdk,
            "select_json_asset_content",
            return_value={"target_simulator": simulator},
        ) as config_asset,
    ):
        result = test_module.estimate_task_resources(
            json_model=TaskLaunchSubmit(task_type=TaskType.circuit_simulation, config_id=uuid4()),
            db_client=db_client,
            task_definition=TASK_DEFINITIONS[TaskType.circuit_simulation_neurodamus_cluster],
            compute_cell="cell_b",
        )
    return result.instances, config_asset


def test_the_failed_job_gets_the_two_nodes_it_ran_on():
    """It ran out of memory on one node, and ran in 1 h 45 min on two (job 01a1eea9)."""
    # 1.15 * 1.1 * (0.0055 * 9,587 + 3.5e-6 * 219.1M) = 1,037 GB, over 670 GB usable per node.
    assert _estimate_counted(FAILED_JOB)[0] == 2


def test_neuron_needs_less_memory_than_coreneuron():
    simulation = {"number_neurons": 9_587, "number_synapses": 300_000_000}

    neuron, config_asset = _estimate_counted(simulation, simulator="NEURON")
    coreneuron, _ = _estimate_counted(simulation)

    assert (neuron, coreneuron) == (2, 3)  # 1,269 and 1,396 GB over 670 GB
    assert config_asset.call_args.kwargs["selection"] == {"label": "sonata_simulation_config"}


def test_the_estimate_is_never_below_the_per_cell_floor():
    few_synapses = {"number_neurons": 1_000_000, "number_synapses": 10}

    floor = math.ceil(test_module.MIN_GB_PER_CELL * 1_000_000 / 788)
    assert _estimate_counted(few_synapses)[0] == floor == 39


def test_counted_synapses_lift_the_temporary_per_cell_rule():
    """Counted synapses replace the stopgap: an SSCX-like simulation gets the 0.03 floor."""
    sscx = {"number_neurons": 20_000, "number_synapses": 20_000 * 2_400}

    assert _estimate_counted(sscx)[0] == math.ceil(0.03 * 20_000 / 788) == 1
    assert math.ceil(test_module.MEM_GB_PER_CELL * 20_000 / 788) == 3


def test_a_simulation_without_synapses_keeps_the_per_cell_rule():
    nodes, config_asset = _estimate_counted({"number_neurons": 9_587})

    assert nodes == math.ceil(test_module.MEM_GB_PER_CELL * 9_587 / 788)
    config_asset.assert_not_called()
