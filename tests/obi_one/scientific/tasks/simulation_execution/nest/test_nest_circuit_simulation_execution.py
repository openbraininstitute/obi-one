from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from obi_one.scientific.tasks.simulation_execution.nest.config import (
    NestCircuitSimulationExecutionSingleConfig,
)
from obi_one.scientific.tasks.simulation_execution.nest.task import (
    NestCircuitSimulationExecutionTask,
)

_BASE = "obi_one.scientific.tasks.simulation_execution.task"
_TASK = "obi_one.scientific.tasks.simulation_execution.nest.task"
_LIB = "obi_one.scientific.library.simulation.nest.simulate_nest"


@pytest.fixture
def simulation_entity():
    entity = MagicMock()
    entity.id = UUID("12345678-1234-5678-1234-567812345678")
    entity.entity_id = UUID("87654321-4321-8765-4321-876543218765")
    return entity


@pytest.fixture
def config(tmp_path, simulation_entity):
    task_config = NestCircuitSimulationExecutionSingleConfig(
        idx=0,
        scan_output_root=tmp_path,
        coordinate_output_root=tmp_path / "coord",
    )
    task_config.set_single_entity(simulation_entity)
    return task_config


@pytest.fixture
def db_client(simulation_entity):
    client = MagicMock()
    circuit_entity = MagicMock()
    circuit_entity.id = simulation_entity.entity_id
    client.get_entity.return_value = circuit_entity
    return client


@patch(f"{_LIB}.run_simulation")
@patch(f"{_BASE}.stage_simulation")
@patch(f"{_TASK}.stage_circuit")
@patch(f"{_TASK}.db_sdk.get_identifiable")
def test_execute_local_skips_registration(
    mock_get_identifiable,
    mock_stage_circuit,
    mock_stage_simulation,
    mock_run_simulation,
    config,
    db_client,
    simulation_entity,
    tmp_path,
):
    mock_get_identifiable.return_value = simulation_entity
    mock_stage_circuit.return_value = MagicMock(path=tmp_path / "circuit.json")
    mock_stage_simulation.return_value = tmp_path / "simulation_config.json"
    mock_run_simulation.return_value = tmp_path / "spikes.h5"

    task = NestCircuitSimulationExecutionTask(config=config)
    task.execute(db_client=db_client, execution_activity_id=None)

    mock_stage_circuit.assert_called_once()
    mock_stage_simulation.assert_called_once()
    mock_run_simulation.assert_called_once_with(tmp_path / "simulation_config.json")
    db_client.update_entity.assert_not_called()


@patch(f"{_BASE}.register_simulation_results")
@patch(f"{_LIB}.run_simulation")
@patch(f"{_BASE}.stage_simulation")
@patch(f"{_TASK}.stage_circuit")
@patch(f"{_TASK}.db_sdk.get_identifiable")
def test_execute_tracked_registers_spike_report(
    mock_get_identifiable,
    mock_stage_circuit,
    mock_stage_simulation,
    mock_run_simulation,
    mock_register,
    config,
    db_client,
    simulation_entity,
    tmp_path,
):
    mock_get_identifiable.return_value = simulation_entity
    execution_activity = MagicMock()
    execution_activity.id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    db_client.get_entity.side_effect = [execution_activity, MagicMock()]
    mock_stage_circuit.return_value = MagicMock(path=tmp_path / "circuit.json")
    mock_stage_simulation.return_value = tmp_path / "simulation_config.json"
    spike_report_file = tmp_path / "spikes.h5"
    mock_run_simulation.return_value = spike_report_file
    generated_entity = MagicMock()
    generated_entity.id = UUID("11111111-2222-3333-4444-555555555555")
    mock_register.return_value = generated_entity

    task = NestCircuitSimulationExecutionTask(config=config)
    task.execute(db_client=db_client, execution_activity_id=execution_activity.id)

    mock_register.assert_called_once()
    assert mock_register.call_args.kwargs["spike_report_file"] == spike_report_file
    assert mock_register.call_args.kwargs["voltage_report_files"] == []
    db_client.update_entity.assert_called_once_with(
        entity_id=execution_activity.id,
        entity_type=NestCircuitSimulationExecutionTask.activity_type,
        attrs_or_entity={"generated_ids": [str(generated_entity.id)]},
    )
