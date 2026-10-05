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


# Formulas in estimate_task_resources:
#   memory_gb = 1 + cells * (0.01 + electrodes * 3e-5), never below the defaults (1 core, 8 GB)
#   hours = ceil((900 + cells * 0.6) / 3600), never below the default (2 h)


@pytest.mark.parametrize(
    ("scale", "n_cells", "electrodes", "exp_cores", "exp_memory", "exp_timelimit"),
    [
        # 10 cells: 1.1 GB, under the defaults
        (CircuitScale.small, 10, (16,), 1, 8, "02:00"),
        # nbS1-HEX0-L1: 291 cells, 4.1 GB, under the defaults
        (CircuitScale.microcircuit, 291, (16,), 1, 8, "02:00"),
        # nbS1-HEX0-L4: 4870 cells, 52.0 GB -> (8, 60), 1.06 h
        (CircuitScale.microcircuit, 4870, (16,), 8, 60, "02:00"),
        # 11000 cells: 116.3 GB -> (16, 120), 2.08 h
        (CircuitScale.microcircuit, 11_000, (16,), 16, 120, "03:00"),
        # 291 cells and a 960-electrode array: 12.3 GB -> (2, 16)
        (CircuitScale.microcircuit, 291, (960,), 2, 16, "02:00"),
        # electrodes from every probe count: 291 cells, 2 x 480 electrodes, the same 12.3 GB
        (CircuitScale.microcircuit, 291, (480, 480), 2, 16, "02:00"),
    ],
    ids=["small", "microcircuit_l1", "microcircuit_l4", "large", "many_electrodes", "two_probes"],
)
def test_resources_scale_with_cells_and_electrodes(
    json_model, task_definition, scale, n_cells, electrodes, exp_cores, exp_memory, exp_timelimit
):
    result = _estimate(
        json_model, task_definition, scale=scale, n_cells=n_cells, n_electrodes_per_probe=electrodes
    )

    assert (result.cores, result.memory, result.timelimit) == (exp_cores, exp_memory, exp_timelimit)
    assert result.compute_cell == "cell_b"


@pytest.mark.parametrize(
    ("n_cells", "electrodes", "expected"),
    [
        # nbS1-HEX0: 1 + 30190 * 0.01048 = 317 GB, and still 303 GB without electrodes
        (
            30_190,
            (16,),
            (
                "(30,190 cells, 16 electrodes) needs about 317 GB of memory, more than the"
                " largest machine has (120 GB). Use a smaller circuit."
            ),
        ),
        # 1 + 5000 * 0.0388 = 195 GB, but 51 GB without electrodes
        (
            5_000,
            (960,),
            (
                "(5,000 cells, 960 electrodes) needs about 195 GB of memory, more than the"
                " largest machine has (120 GB). Use fewer electrodes or a smaller circuit."
            ),
        ),
    ],
    ids=["too_many_cells", "too_many_electrodes"],
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

    assert exc_info.value.error_code == ApiErrorCode.INVALID_REQUEST
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
