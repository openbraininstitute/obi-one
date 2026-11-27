import math
from types import SimpleNamespace
from unittest.mock import Mock, call, patch
from uuid import uuid4

import pytest
from entitysdk import models
from entitysdk.types import AssetLabel
from pydantic import ValidationError

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
            ClusterInstanceInfo(
                name="big", max_neurons=10, memory_per_instance_gb=100, ranks_per_instance=4
            ),
            ClusterInstanceInfo(
                name="small", max_neurons=8, memory_per_instance_gb=10, ranks_per_instance=4
            ),
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
                ranks_per_instance=4,
            ),
        ]
    }
    expected_instances = math.ceil(
        test_module.MEMORY_MODEL.uncounted_gb_per_cell * number_neurons / memory_per_instance_gb
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
            ClusterInstanceInfo(
                name="big-only", max_neurons=10, memory_per_instance_gb=32, ranks_per_instance=4
            ),
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


# The CA1 job 01a1cb34 on cell_a: 9,587 cells and 219.1M synapses, 5.4% of the CA3 sources
# replayed with one spike each. It ran out of memory on one node of 768 GB with 192 ranks, and ran
# on two.
FAILED_JOB = {
    "number_neurons": 9_587,
    "number_synapses": 219_103_973,
    "number_synapses_in_replay": 10_903_152,
    "number_spikes_in_replay": 14_548,
}
LARGE = ClusterInstanceInfo(
    name="large", max_neurons=10**6, memory_per_instance_gb=768, ranks_per_instance=192
)


def _simulation(**fields):
    return SimpleNamespace(recording_arrays=[], entity_id=uuid4(), **fields)


def _estimate_counted(simulation, db_client=None):
    db_client = db_client or Mock()
    db_client.get_entity.return_value = simulation
    with patch.object(test_module, "CLUSTER_INSTANCES_INFO", {"cell_a": [LARGE]}):
        result = test_module.estimate_task_resources(
            json_model=TaskLaunchSubmit(task_type=TaskType.circuit_simulation, config_id=uuid4()),
            db_client=db_client,
            task_definition=TASK_DEFINITIONS[TaskType.circuit_simulation_neurodamus_cluster],
            compute_cell="cell_a",
        )
    return result.instances


def test_the_failed_job_gets_the_two_nodes_it_ran_on():
    simulation = _simulation(**FAILED_JOB)

    assert _estimate_counted(simulation) == 2
    # It does not fit one node: what the model gives it is more than the usable memory.
    one_node = test_module.MEMORY_MODEL.peak_memory_safety_factor * (
        LARGE.ranks_per_instance * test_module.MEMORY_MODEL.gb_per_rank
        + test_module.MEMORY_MODEL.gb_per_cell * 9_587
        + test_module.MEMORY_MODEL.gb_per_synapse * 219_103_973
    )
    assert (
        one_node
        > (1 - test_module.MEMORY_MODEL.reserved_node_memory_fraction)
        * LARGE.memory_per_instance_gb
    )


def test_replaying_every_source_costs_more_than_replaying_a_few():
    every_source = FAILED_JOB | {"number_synapses_in_replay": 200_306_893}

    assert test_module.simulation_nodes(_simulation(**every_source), LARGE, Mock()) == 2
    assert (
        test_module.simulation_nodes(
            _simulation(**FAILED_JOB | {"number_synapses": 400_000_000}), LARGE, Mock()
        )
        == 3
    )


def test_a_large_spike_file_costs_on_every_node():
    """10 Hz for 5 s on every CA3 source: 13.4M spikes that each of the 192 ranks reads."""
    poisson = FAILED_JOB | {
        "number_synapses_in_replay": 200_306_893,
        "number_spikes_in_replay": 13_361_900,
    }

    assert _estimate_counted(_simulation(**poisson)) == 3


def test_spike_inputs_that_no_node_can_hold_are_refused():
    too_many = FAILED_JOB | {"number_spikes_in_replay": 100_000_000}

    with pytest.raises(ApiError) as exc_info:
        _estimate_counted(_simulation(**too_many))

    assert exc_info.value.error_code == ApiErrorCode.RESOURCE_ESTIMATION_ERROR
    assert "100,000,000 spikes" in exc_info.value.message


def test_cells_with_few_synapses_keep_the_sscx_rule():
    """nbS1-HEX0 (30,190 cells, 2,650 synapses each) fits one node; the floor gives it two."""
    sscx = _simulation(number_neurons=30_190, number_synapses=30_190 * 2_650)

    assert _estimate_counted(sscx) == math.ceil(0.03 * 30_190 / 768) == 2


@pytest.mark.parametrize("synapses", [{}, {"number_synapses": 0}])
def test_a_simulation_without_counted_synapses_keeps_the_per_cell_rule(synapses):
    """entitycore gives 0 synapses to simulations generated before the counts existed."""
    simulation = _simulation(number_neurons=9_587, **synapses)

    assert _estimate_counted(simulation) == math.ceil(
        test_module.MEMORY_MODEL.uncounted_gb_per_cell * 9_587 / 768
    )


def _lfp_client(simulation, *, weights_gb, circuit_neurons):
    array_id, circuit_id = uuid4(), simulation.entity_id
    simulation.recording_arrays = [SimpleNamespace(id=array_id)]
    weights = SimpleNamespace(
        label=AssetLabel.electrode_array_weight_matrix, size=int(weights_gb * 2**30)
    )
    image = SimpleNamespace(label=AssetLabel.electrode_array_image, size=10**9)
    entities = {
        models.Simulation: simulation,
        models.SimulatableExtracellularRecordingArray: SimpleNamespace(
            assets=[weights, image], circuit_id=circuit_id
        ),
        models.Circuit: SimpleNamespace(number_neurons=circuit_neurons),
    }
    db_client = Mock()
    db_client.get_entity.side_effect = lambda *, entity_type, **_: entities[entity_type]
    db_client.select_assets.side_effect = lambda entity, selection: iter(
        [a for a in entity.assets if a.label == selection["label"]]
    )
    return db_client


def test_lfp_counts_the_weights_of_the_simulated_cells():
    """A tenth of the circuit counts at most a quarter of the weights: 2.5 times its share."""
    simulation = _simulation(**FAILED_JOB)
    db_client = _lfp_client(simulation, weights_gb=400, circuit_neurons=95_870)

    assert test_module.lfp_weights_gb(simulation, db_client) == pytest.approx(100)


def test_lfp_counts_at_most_the_whole_weight_matrix():
    simulation = _simulation(**FAILED_JOB)
    db_client = _lfp_client(simulation, weights_gb=0.7, circuit_neurons=9_587)

    assert test_module.lfp_weights_gb(simulation, db_client) == pytest.approx(0.7)


def test_lfp_weights_add_to_the_memory():
    """The CA1 job with a weight matrix of 600 GB needs a third node."""
    simulation = _simulation(**FAILED_JOB)
    db_client = _lfp_client(simulation, weights_gb=600, circuit_neurons=9_587)

    assert _estimate_counted(simulation, db_client) == 3


def test_a_simulation_needing_more_nodes_than_available_is_refused():
    """The whole rCA1 circuit needs 54 nodes of cell_a, which has 20."""
    limited = LARGE.model_copy(update={"max_instances": 20})
    rca1 = _simulation(number_neurons=456_378, number_synapses=9_943_065_408)

    with pytest.raises(ApiError) as exc_info:
        test_module.simulation_nodes(rca1, limited, Mock())

    assert exc_info.value.error_code == ApiErrorCode.RESOURCE_ESTIMATION_ERROR
    assert "needs 54 nodes" in exc_info.value.message
    assert "at most 20" in exc_info.value.message


def test_a_simulation_within_the_available_nodes_gets_them():
    limited = LARGE.model_copy(update={"max_instances": 2})

    assert test_module.simulation_nodes(_simulation(**FAILED_JOB), limited, Mock()) == 2


def test_the_memory_model_is_frozen():
    with pytest.raises(ValidationError, match="frozen"):
        test_module.MEMORY_MODEL.peak_memory_safety_factor = 1.0


def test_the_memory_model_splits_what_every_node_holds_from_what_nodes_share():
    model = test_module.MemoryModel(
        gb_per_rank=1.0,
        gb_per_replay_spike_per_rank=0.5,
        gb_per_rank_with_lfp=0.25,
        gb_per_cell=2.0,
        gb_per_synapse=0.1,
        gb_per_replayed_synapse=0.01,
        lfp_weights_factor=3.0,
        peak_memory_safety_factor=2.0,
    )

    assert model.per_node_gb(4, 2, lfp=False) == pytest.approx(2.0 * 4 * (1.0 + 0.5 * 2))
    assert model.per_node_gb(4, 2, lfp=True) == pytest.approx(2.0 * 4 * (1.0 + 0.5 * 2 + 0.25))
    assert model.split_gb(10, 100, 50, 7.0) == pytest.approx(
        2.0 * (2.0 * 10 + 0.1 * 100 + 0.01 * 50 + 3.0 * 7.0)
    )
