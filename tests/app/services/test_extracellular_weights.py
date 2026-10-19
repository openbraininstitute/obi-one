import json
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from entitysdk.types import CircuitScale

from app.errors import ApiError, ApiErrorCode
from app.mappings import TASK_DEFINITIONS
from app.schemas.task import TaskLaunchSubmit, TaskType
from app.services.resource_estimation import extracellular_weights as test_module


@pytest.fixture
def task_definition():
    return TASK_DEFINITIONS[TaskType.extracellular_recording_weights_calculation]


@pytest.fixture
def json_model():
    return TaskLaunchSubmit(
        task_type=TaskType.extracellular_recording_weights_calculation,
        config_id=uuid4(),
    )


def _single_config(*n_electrodes_per_probe):
    """A weights config with one linear probe of each given size."""
    return {
        "type": "CreateExtracellularRecordingArraySingleConfig",
        "idx": 0,
        "scan_output_root": "",
        "coordinate_output_root": "",
        "single_coordinate_scan_params": {
            "type": "SingleCoordinateScanParams",
            "scan_params": [],
            "nested_coordinate_subpath_str": "",
        },
        "info": {"type": "Info", "campaign_name": "test", "campaign_description": "test"},
        "initialize": {
            "type": "CreateExtracellularRecordingArrayScanConfig.Initialize",
            "circuit": {"type": "CircuitFromID", "id_str": str(uuid4())},
            "calculation_method": "LineSource",
        },
        "electrode_locations": {
            f"Probe {i}": {
                "type": "LinearExtracellularLocations",
                "n_electrodes": n,
                "spacing": 20.0,
            }
            for i, n in enumerate(n_electrodes_per_probe)
        },
    }


def _estimate(json_model, task_definition, *, scale, n_cells, n_electrodes_per_probe=(16,)):
    circuit_id = uuid4()
    config = SimpleNamespace(inputs=[SimpleNamespace(id=circuit_id)])
    circuit = SimpleNamespace(
        id=circuit_id, name="test circuit", scale=scale, number_neurons=n_cells
    )
    db_client = Mock()
    db_client.get_entity.side_effect = [config, circuit]
    db_client.download_content.return_value = json.dumps(
        _single_config(*n_electrodes_per_probe)
    ).encode()

    with patch(
        "app.services.resource_estimation.extracellular_weights.db_sdk.get_entity_asset_by_label",
        return_value=SimpleNamespace(id=uuid4()),
    ):
        return test_module.estimate_task_resources(
            json_model=json_model,
            db_client=db_client,
            task_definition=task_definition,
            compute_cell="cell_b",
        )


# Formulas in estimate_task_resources, with at least 1, 2, 4, 8 or 16 CPUs for up to 100 cells each,
# and an MPI process on each CPU:
#   memory_gb = cpus * (0.5 + 50 * 0.01 + electrodes * 3.2e-5) + cells * 2.5e-4, never below the
#     default 8 GB
#   weights_gb = cells * electrodes * 8e-6; storage = ceil(15 + weights_gb) when that is over 20 GB
#   hours = ceil((900 + cells * 4 / cpus + weights_gb * 30) / 3600), never below the default (2 h)


@pytest.mark.parametrize(
    ("scale", "n_cells", "electrodes", "exp_cores", "exp_memory", "exp_timelimit", "exp_storage"),
    [
        # 10 cells, 1 process: 1.0 GB, under the defaults
        (CircuitScale.small, 10, (16,), 1, 8, "02:00", None),
        # 150 cells, 2 processes: 2.0 GB -> (2, 4), raised to the default 8 GB
        (CircuitScale.small, 150, (16,), 2, 8, "02:00", None),
        # nbS1-HEX0-L1: 291 cells, 4 processes: 4.1 GB -> (4, 8)
        (CircuitScale.microcircuit, 291, (16,), 4, 8, "02:00", None),
        # 800 cells, 8 processes: 8.2 GB -> (8, 16)
        (CircuitScale.microcircuit, 800, (16,), 8, 16, "02:00", None),
        # nbS1-HEX0-L4: 4870 cells, 16 processes: 17.2 GB -> (16, 32)
        (CircuitScale.microcircuit, 4870, (16,), 16, 32, "02:00", None),
        # 10000 cells, 16 processes: 18.5 GB -> (16, 32), a 1.3 GB file
        (CircuitScale.microcircuit, 10_000, (16,), 16, 32, "02:00", None),
        # 291 cells and a 960-electrode array: 4.2 GB -> (4, 8), a 2.2 GB file
        (CircuitScale.microcircuit, 291, (960,), 4, 8, "02:00", None),
        # electrodes from every probe count: 291 cells, 2 x 480 electrodes, the same
        (CircuitScale.microcircuit, 291, (480, 480), 4, 8, "02:00", None),
        # 400 cells and 4200 electrodes: a 13.4 GB file, so 29 GB of disk
        (CircuitScale.microcircuit, 400, (4200,), 4, 8, "02:00", 29),
        # 10000 cells and 2300 electrodes: 19.7 GB -> (16, 32), and a 184 GB file, so 199 GB of
        # disk and 900 + 2500 + 5520 s -> 3 h
        (CircuitScale.microcircuit, 10_000, (2300,), 16, 32, "03:00", 199),
        # nbS1-O1: 211712 cells, 16 processes: 68.9 GB -> (16, 96), a 27 GB file so 43 GB of disk,
        # and 900 + 52928 + 813 s -> 16 h
        (CircuitScale.microcircuit, 211_712, (16,), 16, 96, "16:00", 43),
    ],
    ids=[
        "small",
        "small_two_processes",
        "microcircuit_l1",
        "microcircuit_eight_processes",
        "microcircuit_l4",
        "large",
        "many_electrodes",
        "two_probes",
        "disk_for_the_weights",
        "largest_weights",
        "nbs1_o1",
    ],
)
def test_resources_scale_with_cells_and_electrodes(
    json_model,
    task_definition,
    scale,
    n_cells,
    electrodes,
    exp_cores,
    exp_memory,
    exp_timelimit,
    exp_storage,
):
    result = _estimate(
        json_model, task_definition, scale=scale, n_cells=n_cells, n_electrodes_per_probe=electrodes
    )

    assert (result.cores, result.memory, result.timelimit) == (exp_cores, exp_memory, exp_timelimit)
    # Serialized as the launch sends it
    assert result.model_dump(mode="json")["ephemeral_storage"] == exp_storage
    assert result.compute_cell == "cell_b"


def test_timelimit_is_split_between_processes(json_model, task_definition, monkeypatch):
    # 2000 cells, 16 processes: 900 + 2000 * 60 / 16 = 8400 s -> 3 h
    monkeypatch.setattr(test_module, "SECONDS_PER_CELL", 60.0)

    result = _estimate(json_model, task_definition, scale=CircuitScale.microcircuit, n_cells=2000)

    assert (result.cores, result.timelimit) == (16, "03:00")


@pytest.mark.parametrize(
    ("n_cells", "electrodes", "expected"),
    [
        # 500000 * 2.5e-4 + 16 * 1.0 = 141 GB, and still 141 GB without electrodes
        (
            500_000,
            (16,),
            (
                "(500,000 cells, 16 electrodes) needs about 141 GB of memory, more than the"
                " largest machine has (120 GB). Use a smaller circuit."
            ),
        ),
        # 0.25 + 16 * 8.04 = 129 GB, but 16 GB without electrodes
        (
            1_000,
            (220_000,),
            (
                "(1,000 cells, 220,000 electrodes) needs about 129 GB of memory, more than the"
                " largest machine has (120 GB). Use fewer electrodes or a smaller circuit."
            ),
        ),
        # 10000 * 2400 * 8e-6 = 192 GB, and 15 GB more for the job
        (
            10_000,
            (2400,),
            (
                "(10,000 cells, 2,400 electrodes) writes a weights file of up to 192 GB, more"
                " than the 200 GB of storage a task can have. Use fewer electrodes or a smaller"
                " circuit."
            ),
        ),
    ],
    ids=["too_many_cells", "too_many_electrodes_for_memory", "too_many_electrodes_for_disk"],
)
def test_too_large_circuit_is_rejected(json_model, task_definition, n_cells, electrodes, expected):
    with pytest.raises(ApiError) as exc_info:
        _estimate(
            json_model,
            task_definition,
            scale=CircuitScale.microcircuit,
            n_cells=n_cells,
            n_electrodes_per_probe=electrodes,
        )

    assert exc_info.value.error_code == ApiErrorCode.RESOURCE_ESTIMATION_ERROR
    assert exc_info.value.http_status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert exc_info.value.message == (
        f"Calculating extracellular recording weights for 'test circuit' {expected}"
    )


@pytest.mark.parametrize(
    "scale", [CircuitScale.region, CircuitScale.system, CircuitScale.whole_brain]
)
def test_scale_larger_than_microcircuit_is_rejected(json_model, task_definition, scale):
    with pytest.raises(ApiError) as exc_info:
        _estimate(json_model, task_definition, scale=scale, n_cells=100)

    assert exc_info.value.error_code == ApiErrorCode.INVALID_REQUEST
    assert exc_info.value.http_status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert f"'{scale}'" in exc_info.value.message
    for supported in test_module.SUPPORTED_CIRCUIT_SCALES:
        assert f"'{supported.value}'" in exc_info.value.message


def test_missing_input_circuit_is_rejected(json_model, task_definition):
    db_client = Mock()
    db_client.get_entity.side_effect = [SimpleNamespace(inputs=[])]

    with pytest.raises(ApiError) as exc_info:
        test_module.estimate_task_resources(
            json_model=json_model,
            db_client=db_client,
            task_definition=task_definition,
            compute_cell="cell_b",
        )

    assert exc_info.value.error_code == ApiErrorCode.INVALID_REQUEST
    assert exc_info.value.http_status_code == HTTPStatus.UNPROCESSABLE_ENTITY
