from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import entitysdk
import pytest
from obp_accounting_sdk.constants import ServiceSubtype

from app.errors import ApiError, ApiErrorCode
from app.mappings import TASK_DEFINITIONS
from app.schemas.accounting import AccountingParameters
from app.schemas.task import TaskLaunchSubmit, TaskType
from app.services.resource_estimation import circuit_extraction as test_module
from obi_one.scientific.library.circuit_constants import EdgePopulationType, NodePopulationType
from obi_one.scientific.library.circuit_metrics import (
    CircuitMetricsEdgePopulation,
    CircuitMetricsNodePopulation,
    CircuitMetricsOutput,
)

OPTIONS_HINT = (
    "Extract fewer neurons, or turn off including virtual and/or creating external populations."
)


@pytest.fixture
def db_client():
    """Database client."""
    return entitysdk.Client(api_url="http://my-url", token_manager="my-token")  # ruff: ignore[hardcoded-password-func-arg]


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
    assert test_module.get_required_cpu_memory_combo(mem_required) == expected


@pytest.mark.parametrize(
    ("mem_required", "min_cpus", "expected"),
    [
        (1, 2, (2, 4)),
        (5, 4, (4, 8)),
        (10, 4, (4, 16)),
        (59, 16, (16, 64)),
    ],
)
def test_get_required_cpu_memory_combo_with_min_cpus(mem_required, min_cpus, expected):
    assert test_module.get_required_cpu_memory_combo(mem_required, min_cpus=min_cpus) == expected


@pytest.mark.parametrize(
    ("mem_required", "min_cpus", "expected"),
    [
        # 4 CPUs: 5 + 4 * 0.5 = 7 GB
        (5, 4, (4, 8)),
        # 4 CPUs: 29.2 + 2 = 31.2 GB is over their 30 GB, and 8 CPUs need 29.2 + 4 = 33.2 GB
        (29.2, 4, (8, 48)),
    ],
)
def test_get_required_cpu_memory_combo_with_memory_per_cpu(mem_required, min_cpus, expected):
    assert (
        test_module.get_required_cpu_memory_combo(
            mem_required, min_cpus=min_cpus, mem_gb_per_cpu=0.5
        )
        == expected
    )


def test_get_required_cpu_memory_combo_too_large():
    with pytest.raises(ValueError, match="No CPU/memory combination found"):
        test_module.get_required_cpu_memory_combo(200)


def test_get_required_extra_storage_space_default():
    # Under 20 GB -> no extra storage needed
    assert test_module.get_required_extra_storage_space(10.0) is None


def test_get_required_extra_storage_space_extra():
    # Between 20 and 200 GB -> allocate extra storage (ceiling)
    assert test_module.get_required_extra_storage_space(25.0) == 25
    assert test_module.get_required_extra_storage_space(25.3) == 26
    # A numpy integer would compare equal but fail the launch's JSON serialization
    assert type(test_module.get_required_extra_storage_space(25.3)) is int


def test_get_required_extra_storage_space_too_large():
    with pytest.raises(ValueError, match="Not enough disk space"):
        test_module.get_required_extra_storage_space(250.0)


def _node_population(name, population_type, number_of_nodes):
    return CircuitMetricsNodePopulation(
        number_of_nodes=number_of_nodes,
        name=name,
        population_type=population_type,
        property_names=[],
        property_unique_values={},
        property_value_counts={},
        node_location_info=None,
    )


def _edge_population(name, source_name, number_of_edges):
    """Chemical edge population from source_name onto the biophysical population."""
    return CircuitMetricsEdgePopulation(
        number_of_edges=number_of_edges,
        name=name,
        population_type=EdgePopulationType.chemical,
        source_name=source_name,
        target_name="bio_pop",
        property_names=[],
        property_stats=None,
        degree_stats=None,
    )


def _make_circuit_metrics(
    nbio_nodes, nvirt_nodes, sbio_edges, svirt_edges, external_neurons=0, external_synapses=0
):
    """Helper to build a CircuitMetricsOutput with given node/edge counts.

    Node populations: "bio_pop" (biophysical), "virt_pop" (afferent virtual) and, if external
    neurons or synapses are given, "external_pop" (virtual, externalized by an earlier extraction).
    Edge populations: one from each node population onto "bio_pop".
    """
    bio_nodes = [_node_population("bio_pop", NodePopulationType.biophysical, nbio_nodes)]
    virtual_nodes = [_node_population("virt_pop", NodePopulationType.virtual, nvirt_nodes)]
    edges = [
        _edge_population("bio_edges", "bio_pop", sbio_edges),
        _edge_population("virt_edges", "virt_pop", svirt_edges),
    ]
    if external_neurons or external_synapses:
        virtual_nodes.append(
            _node_population("external_pop", NodePopulationType.virtual, external_neurons)
        )
        edges.append(_edge_population("external_edges", "external_pop", external_synapses))
    return CircuitMetricsOutput(
        number_of_biophys_node_populations=len(bio_nodes),
        number_of_virtual_node_populations=len(virtual_nodes),
        number_of_point_node_populations=0,
        names_of_biophys_node_populations=[pop.name for pop in bio_nodes],
        names_of_virtual_node_populations=[pop.name for pop in virtual_nodes],
        names_of_point_node_populations=[],
        names_of_nodesets=[],
        biophysical_node_populations=bio_nodes,
        virtual_node_populations=virtual_nodes,
        point_node_populations=[],
        number_of_chemical_edge_populations=len(edges),
        number_of_electrical_edge_populations=0,
        names_of_chemical_edge_populations=[pop.name for pop in edges],
        names_of_electrical_edge_populations=[],
        chemical_edge_populations=edges,
        electrical_edge_populations=[],
    )


def _run_estimate_task_resources(
    db_client, circuit_metrics, do_virtual, accounting_parameters=None, *, create_external=True
):
    """Run estimate_task_resources for circuit_extraction with mocked dependencies."""
    task_definition = TASK_DEFINITIONS[TaskType.circuit_extraction]
    json_model = TaskLaunchSubmit(task_type=TaskType.circuit_extraction, config_id=uuid4())
    fake_config = SimpleNamespace(
        initialize=SimpleNamespace(do_virtual=do_virtual, create_external=create_external)
    )
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
            "app.services.resource_estimation.circuit_extraction.get_task_spec_for_task_type",
            return_value=SimpleNamespace(asset_label="circuit_extraction_config"),
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
            accounting_parameters=accounting_parameters,
        )


# Formulas in estimate_task_resources (synapses of the input, input_synapses, as counted below):
#   input_synapses = sbio + (svirt if do_virtual) + (sext if create_external)
#   mem_gb_required = 1.2 * min(24, 2 + 0.04e-6 * input_synapses)
#   time_h = ceil(1 + 2 * (0.4e-9 * input_synapses + 10.5e-9 * output_synapses))
#   disk_gb = 1 + output_synapses * 3.9e-7
@pytest.mark.parametrize(
    ("nbio", "nvirt", "sbio", "svirt", "do_virtual", "exp_cores", "exp_mem", "exp_time"),
    [
        # Small circuit: 50k + 20k synapses, do_virtual=True
        #   mem=2.4 -> (1,4), time=ceil(1 + 2 * 0.0007)=2
        (1000, 500, 50_000, 20_000, True, 1, 4, "02:00"),
        # Small circuit: 50k bio synapses, do_virtual=False (virtual synapses ignored)
        (1000, 500, 50_000, 20_000, False, 1, 4, "02:00"),
        # Medium circuit: 100M + 50M synapses, do_virtual=True
        #   mem=9.6 -> (2,12), time=ceil(1 + 2 * (0.06 + 1.575))=5
        (100_000, 50_000, 100_000_000, 50_000_000, True, 2, 12, "05:00"),
        # Medium circuit: 100M bio synapses, do_virtual=False
        #   mem=7.2 -> (1,8), time=ceil(1 + 2 * (0.04 + 1.05))=4
        (100_000, 50_000, 100_000_000, 50_000_000, False, 1, 8, "04:00"),
        # Large circuit: 300M + 100M synapses, do_virtual=True
        #   mem=21.6 -> (4,24), time=ceil(1 + 2 * (0.16 + 4.2))=10
        (500_000, 200_000, 300_000_000, 100_000_000, True, 4, 24, "10:00"),
        # Large circuit: 300M bio synapses, do_virtual=False
        #   mem=16.8 -> (4,24), time=ceil(1 + 2 * (0.12 + 3.15))=8
        (500_000, 200_000, 300_000_000, 100_000_000, False, 4, 24, "08:00"),
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


# Parents of the re-extraction benchmarks, as arguments of _make_circuit_metrics (biophysical and
# afferent virtual neurons and synapses, then externalized virtual neurons and synapses)
BENCHMARK_PARENTS = {
    "nbS1": (4_234_929, 471_368, 9_138_314_390, 963_362_379, 0, 0),
    "nbS1-O1": (211_712, 24_794, 407_127_134, 49_185_245, 549_126, 104_319_446),
    "nbS1-HEX0": (30_190, 8_866, 41_299_369, 6_829_766, 270_943, 31_867_946),
    "rCA1": (456_378, 1_267_238, 820_867_760, 9_122_197_648, 0, 0),
    "rCA1-CYLINDER-REF": (6_213, 267_238, 7_115_120, 124_506_110, 26_985, 4_079_149),
}


@pytest.mark.parametrize(
    ("parent", "extracted", "peak_gb", "typical_h"),
    [
        # Allocations must exceed the measured peak memory and the typical run time; for the small
        # parents also the worst case (runs with a slow split step, cause unknown).
        ("nbS1", 211_712, 22.9, 14.5),
        ("nbS1-O1", 30_190, 17.0, 1.5),
        ("nbS1-HEX0", 12_025, 2.3, 1.1),
        ("rCA1", 17_647, 15.9, 6.1),
        ("rCA1-CYLINDER-REF", 9, 5.4, 0.6),
    ],
)
def test_estimate_task_resources_benchmarks(db_client, parent, extracted, peak_gb, typical_h):
    metrics = _make_circuit_metrics(*BENCHMARK_PARENTS[parent])
    accounting_parameters = AccountingParameters(
        count=extracted, service_subtype=ServiceSubtype.CIRCUIT_EXTRACTION
    )
    result = _run_estimate_task_resources(
        db_client, metrics, do_virtual=True, accounting_parameters=accounting_parameters
    )
    assert result.memory > peak_gb
    assert int(result.timelimit.split(":")[0]) > typical_h


@pytest.mark.parametrize(
    ("sbio", "svirt", "do_virtual"),
    [
        # do_virtual=True: total = 300M + 300M = 600M synapses
        #   disk = 1 + 600e6 * 3.9e-7 = 235 GB > 200 GB limit (time: 15 h)
        (300_000_000, 300_000_000, True),
        # do_virtual=False: only bio = 600M synapses
        #   disk = 1 + 600e6 * 3.9e-7 = 235 GB > 200 GB limit (time: 15 h)
        (600_000_000, 300_000_000, False),
    ],
    ids=["too_many_synapses_with_virtual", "too_many_synapses_without_virtual"],
)
def test_estimate_task_resources_disk_space_limit(db_client, sbio, svirt, do_virtual):
    metrics = _make_circuit_metrics(1000, 500, sbio, svirt)
    with pytest.raises(ApiError) as exc_info:
        _run_estimate_task_resources(db_client, metrics, do_virtual)

    assert exc_info.value.error_code == ApiErrorCode.RESOURCE_ESTIMATION_ERROR
    assert exc_info.value.http_status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "about 600,000,000 synapses" in exc_info.value.message
    assert "more than the 200 GB of storage a task can have" in exc_info.value.message
    assert exc_info.value.message.endswith(OPTIONS_HINT)


def test_estimate_task_resources_memory_limit(db_client):
    """The memory saturates with the circuit size, so test the error with an unavailable machine."""
    metrics = _make_circuit_metrics(1000, 0, 1_000_000_000, 0)
    with (
        patch.object(test_module, "get_required_cpu_memory_combo", side_effect=ValueError),
        pytest.raises(ApiError) as exc_info,
    ):
        _run_estimate_task_resources(db_client, metrics, do_virtual=False, create_external=False)
    assert exc_info.value.error_code == ApiErrorCode.RESOURCE_ESTIMATION_ERROR
    assert exc_info.value.http_status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert exc_info.value.message == (
        "Extracting 1,000 neurons needs about 29 GB of memory, more than the largest"
        " machine has (120 GB). Extract fewer neurons."
    )


@pytest.mark.parametrize(
    ("sbio", "svirt", "do_virtual"),
    [
        # do_virtual=False: only bio = 60M, disk = 1 + 60e6*3.9e-7 = 24.4 GB
        (60_000_000, 50_000_000, False),
    ],
    ids=["under_limit_without_virtual"],
)
def test_estimate_task_resources_disk_ok_without_virtual(db_client, sbio, svirt, do_virtual):
    """With do_virtual=False, virtual synapses are excluded and disk check passes."""
    metrics = _make_circuit_metrics(1000, 500, sbio, svirt)
    result = _run_estimate_task_resources(db_client, metrics, do_virtual)
    assert result.cores >= 1


def test_estimate_task_resources_with_accounting_parameters_reduces_disk(db_client):
    """When accounting_parameters.count < nbio, output_fraction scales down disk estimate."""
    # nbio=100_000, sbio=500M synapses
    # Without accounting_parameters: output_fraction=1.0
    #   disk = 1 + 500e6 * 3.9e-7 = 196 GB -> extra storage = 200 (in steps of 50 GB)
    # With count=5_000 (5% of nbio): output_fraction=0.05
    #   disk = 1 + 500e6 * 0.05 * 3.9e-7 = 10.75 GB -> no extra storage (None)
    metrics = _make_circuit_metrics(100_000, 0, 500_000_000, 0)

    result_without = _run_estimate_task_resources(db_client, metrics, do_virtual=False)
    assert result_without.model_dump(mode="json")["ephemeral_storage"] == 200

    accounting_params = AccountingParameters(
        count=5_000,
        service_subtype=ServiceSubtype.CIRCUIT_EXTRACTION,
    )
    result_with = _run_estimate_task_resources(
        db_client, metrics, do_virtual=False, accounting_parameters=accounting_params
    )
    assert result_with.ephemeral_storage is None


def test_estimate_task_resources_with_accounting_parameters_full_extraction(db_client):
    """When accounting_parameters.count == nbio, output_fraction is 1.0 (same as None)."""
    # nbio=100_000, sbio=500M synapses, count=100_000 -> fraction=1.0
    #   disk = 1 + 500e6 * 3.9e-7 = 196 GB -> extra storage = 200 (in steps of 50 GB)
    metrics = _make_circuit_metrics(100_000, 0, 500_000_000, 0)

    accounting_params = AccountingParameters(
        count=100_000,
        service_subtype=ServiceSubtype.CIRCUIT_EXTRACTION,
    )
    result = _run_estimate_task_resources(
        db_client, metrics, do_virtual=False, accounting_parameters=accounting_params
    )
    assert result.model_dump(mode="json")["ephemeral_storage"] == 200


def test_estimate_task_resources_with_accounting_parameters_disk_limit(db_client):
    """Even with accounting_parameters, large extractions can exceed the disk limit."""
    # nbio=100_000, sbio=600M synapses, count=100_000 -> fraction=1.0
    #   disk = 1 + 600e6 * 3.9e-7 = 235 GB > 200 GB limit (time: 14 h)
    metrics = _make_circuit_metrics(100_000, 0, 600_000_000, 0)

    accounting_params = AccountingParameters(
        count=100_000,
        service_subtype=ServiceSubtype.CIRCUIT_EXTRACTION,
    )
    with pytest.raises(ApiError, match="more than the 200 GB of storage a task can have"):
        _run_estimate_task_resources(
            db_client, metrics, do_virtual=False, accounting_parameters=accounting_params
        )


@pytest.mark.parametrize(
    ("sbio", "exp_storage"),
    [
        (40_000_000, None),  # 16.6 GB: default storage
        (60_000_000, 50),  # 24.4 GB
        (130_000_000, 100),  # 51.7 GB
        (250_000_000, 100),  # 98.5 GB
        (260_000_000, 150),  # 102.4 GB
        (500_000_000, 200),  # 196 GB
    ],
)
def test_estimate_task_resources_storage_in_steps_of_50_gb(db_client, sbio, exp_storage):
    metrics = _make_circuit_metrics(100_000, 0, sbio, 0)
    result = _run_estimate_task_resources(db_client, metrics, do_virtual=False)
    assert result.model_dump(mode="json")["ephemeral_storage"] == exp_storage


def test_estimate_task_resources_time_limit_at_maximum(db_client):
    """28G input synapses, 10 of 1M neurons extracted: ceil(1 + 2 * 0.4e-9 * 28e9) = 24 h."""
    metrics = _make_circuit_metrics(1_000_000, 0, 28_000_000_000, 0)
    accounting_params = AccountingParameters(
        count=10, service_subtype=ServiceSubtype.CIRCUIT_EXTRACTION
    )
    result = _run_estimate_task_resources(
        db_client, metrics, do_virtual=False, accounting_parameters=accounting_params
    )
    assert result.timelimit == "24:00"


@pytest.mark.parametrize(
    ("nvirt", "do_virtual", "create_external", "hint"),
    [
        # Turning off either option is suggested when it is on, as both reduce the requirements
        (0, False, False, "Extract fewer neurons."),
        (
            500,
            True,
            False,
            OPTIONS_HINT,
        ),
        (
            0,
            False,
            True,
            OPTIONS_HINT,
        ),
        (
            500,
            True,
            True,
            OPTIONS_HINT,
        ),
    ],
)
def test_estimate_task_resources_time_limit_too_long(
    db_client, nvirt, do_virtual, create_external, hint
):
    """29.5G input synapses, 10 of 1M extracted: ceil(1 + 2 * 0.4e-9 * 29.5e9) = 25 h > 24 h."""
    metrics = _make_circuit_metrics(1_000_000, nvirt, 29_500_000_000, 0)
    accounting_params = AccountingParameters(
        count=10, service_subtype=ServiceSubtype.CIRCUIT_EXTRACTION
    )
    with pytest.raises(ApiError) as exc_info:
        _run_estimate_task_resources(
            db_client,
            metrics,
            do_virtual=do_virtual,
            accounting_parameters=accounting_params,
            create_external=create_external,
        )
    assert exc_info.value.error_code == ApiErrorCode.RESOURCE_ESTIMATION_ERROR
    assert exc_info.value.http_status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert exc_info.value.message == (
        f"Extracting {1_000_000 + (nvirt if do_virtual else 0):,} neurons needs about 25 hours,"
        f" more than the 24 hours a task can run. {hint}"
    )


@pytest.mark.parametrize(
    ("do_virtual", "create_external", "exp_mem", "exp_storage"),
    [
        # Input synapses: 50M bio + 100M afferent virtual (do_virtual) + 300M external
        # (create_external); memory = 1.2 * min(24, 2 + 0.04e-6 * synapses), disk in 50 GB steps
        (False, False, 6, 50),  # 50M: 4.8 GB, 20.5 GB
        (True, False, 12, 100),  # 150M: 9.6 GB, 59.5 GB
        (False, True, 24, 150),  # 350M: 19.2 GB, 137.5 GB
        (True, True, 30, 200),  # 450M: 24 GB, 176.5 GB
    ],
)
def test_estimate_task_resources_external_populations_only_count_with_create_external(
    db_client, do_virtual, create_external, exp_mem, exp_storage
):
    metrics = _make_circuit_metrics(
        1000, 500, 50_000_000, 100_000_000, external_neurons=2000, external_synapses=300_000_000
    )
    result = _run_estimate_task_resources(
        db_client, metrics, do_virtual, create_external=create_external
    )
    assert result.memory == exp_mem
    assert result.model_dump(mode="json")["ephemeral_storage"] == exp_storage
