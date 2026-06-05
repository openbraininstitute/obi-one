from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import entitysdk
import pytest

from app.mappings import TASK_DEFINITIONS
from app.schemas.task import TaskLaunchSubmit, TaskType
from app.services.resource_estimation import circuit_extraction as test_module
from obi_one.scientific.library.circuit_metrics import (
    CircuitMetricsEdgePopulation,
    CircuitMetricsNodePopulation,
    CircuitMetricsOutput,
    EdgePopulationType,
    NodePopulationType,
)


@pytest.fixture
def db_client():
    """Database client."""
    return entitysdk.Client(api_url="http://my-url", token_manager="my-token")  # noqa: S106


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


def _run_estimate_task_resources(db_client, circuit_metrics, do_virtual):
    """Run estimate_task_resources for circuit_extraction with mocked dependencies."""
    task_definition = TASK_DEFINITIONS[TaskType.circuit_extraction]
    json_model = TaskLaunchSubmit(task_type=TaskType.circuit_extraction, config_id=uuid4())
    fake_config = SimpleNamespace(initialize=SimpleNamespace(do_virtual=do_virtual))
    circuit_id = uuid4()
    fake_entity = SimpleNamespace(inputs=[SimpleNamespace(id=circuit_id)])

    with (
        patch.object(db_client, "get_entity", return_value=fake_entity),
        patch.object(db_client, "download_content", return_value=b'{"type": "Fake"}'),
        patch(
            "app.services.resource_estimation.circuit_extraction.get_circuit_metrics",
            return_value=circuit_metrics,
        ),
        patch(
            "app.services.resource_estimation.circuit_extraction.deserialize_obi_object_from_json_data",
            return_value=fake_config,
        ),
        patch(
            "app.services.resource_estimation.circuit_extraction.task_registry.get_task_type_config_asset_label",
            return_value="circuit_extraction_config",
        ),
        patch(
            "app.services.resource_estimation.circuit_extraction.db_sdk.get_entity_asset_by_label"
        ) as mock_get_asset,
    ):
        mock_get_asset.return_value = SimpleNamespace(id=uuid4())
        return test_module.estimate_task_resources(
            json_model=json_model,
            db_client=db_client,
            task_definition=task_definition,
            compute_cell="cell_b",
        )


# Formulas in estimate_task_resources:
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
def test_estimate_task_resources_allocation(
    db_client, nbio, nvirt, sbio, svirt, do_virtual, exp_cores, exp_mem, exp_time
):
    metrics = _make_circuit_metrics(nbio, nvirt, sbio, svirt)
    result = _run_estimate_task_resources(db_client, metrics, do_virtual)

    assert result.cores == exp_cores
    assert result.memory == exp_mem
    assert result.timelimit == exp_time


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
def test_estimate_task_resources_disk_space_limit(db_client, sbio, svirt, do_virtual):
    metrics = _make_circuit_metrics(1000, 500, sbio, svirt)
    with pytest.raises(ValueError, match="Not enough disk space"):
        _run_estimate_task_resources(db_client, metrics, do_virtual)


@pytest.mark.parametrize(
    ("sbio", "svirt", "do_virtual"),
    [
        # do_virtual=False: only bio = 60M, disk = 1 + 60e6*1.85e-7 = 12.1 GB < 20
        (60_000_000, 50_000_000, False),
    ],
    ids=["under_limit_without_virtual"],
)
def test_estimate_task_resources_disk_ok_without_virtual(db_client, sbio, svirt, do_virtual):
    """With do_virtual=False, virtual synapses are excluded and disk check passes."""
    metrics = _make_circuit_metrics(1000, 500, sbio, svirt)
    result = _run_estimate_task_resources(db_client, metrics, do_virtual)
    assert result.cores >= 1
