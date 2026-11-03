from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from obi_one.scientific.library.simulation.neuron.schemas import SimulationResults
from obi_one.scientific.tasks.simulation_execution.config import SimulationExecutionSingleConfig
from obi_one.scientific.tasks.simulation_execution.task import SimulationExecutionTask

_TASK = "obi_one.scientific.tasks.simulation_execution.task"
SIMULATION_ID = UUID("12345678-1234-5678-1234-567812345678")
ACTIVITY_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
GENERATED_ID = UUID("11111111-2222-3333-4444-555555555555")


class RecordingTask(SimulationExecutionTask):
    events: ClassVar[list[str]] = []
    run_kwargs: ClassVar[dict] = {}
    results: ClassVar[SimulationResults]

    def _stage_circuit(self, *, db_client, data_dir, simulation_entity):  # ruff: ignore[unused-method-argument]
        self.events.append("stage_circuit")
        circuit = MagicMock()
        circuit.path = data_dir / "circuit_config.json"
        return circuit

    def _run_simulation(self, *, staged_circuit, simulation_config_path, results_dir):
        self.events.append("run")
        self.run_kwargs.update(
            staged_circuit=staged_circuit,
            simulation_config_path=simulation_config_path,
            results_dir=results_dir,
        )
        return self.results


@pytest.fixture
def simulation_entity():
    entity = MagicMock()
    entity.id = SIMULATION_ID
    return entity


@pytest.fixture
def task(tmp_path, simulation_entity):
    RecordingTask.events = []
    RecordingTask.run_kwargs = {}
    RecordingTask.results = SimulationResults(
        spike_report_file=tmp_path / "spikes.h5",
        voltage_report_files=[tmp_path / "soma.h5"],
        lfp_report_files=[tmp_path / "LFP.h5"],
    )
    config = SimulationExecutionSingleConfig(
        idx=0, scan_output_root=tmp_path, coordinate_output_root=tmp_path / "coord"
    )
    config.set_single_entity(simulation_entity)
    return RecordingTask(config=config)


@patch(f"{_TASK}.register_simulation_results")
@patch(f"{_TASK}.stage_simulation")
def test_execute_without_activity_skips_registration(
    mock_stage_simulation, mock_register, task, tmp_path
):
    mock_stage_simulation.side_effect = lambda **_: (
        RecordingTask.events.append("stage_simulation") or tmp_path / "sim_config.json"
    )
    db_client = MagicMock()

    task.execute(db_client=db_client, execution_activity_id=None)

    assert RecordingTask.events == ["stage_circuit", "stage_simulation", "run"]
    assert mock_stage_simulation.call_args.kwargs["circuit_config_path"] == (
        tmp_path / "coord" / "data" / "circuit_config.json"
    )
    assert RecordingTask.run_kwargs["simulation_config_path"] == tmp_path / "sim_config.json"
    assert RecordingTask.run_kwargs["results_dir"] == tmp_path / "coord" / "outputs"
    mock_register.assert_not_called()
    db_client.update_entity.assert_not_called()


@patch(f"{_TASK}.register_simulation_results")
@patch(f"{_TASK}.stage_simulation")
def test_execute_with_activity_registers_results(
    mock_stage_simulation, mock_register, task, tmp_path
):
    mock_stage_simulation.return_value = tmp_path / "sim_config.json"
    execution_activity = MagicMock()
    execution_activity.id = ACTIVITY_ID
    db_client = MagicMock()
    db_client.get_entity.return_value = execution_activity
    mock_register.return_value = MagicMock(id=GENERATED_ID)

    task.execute(db_client=db_client, execution_activity_id=ACTIVITY_ID)

    db_client.get_entity.assert_called_once_with(
        entity_id=ACTIVITY_ID, entity_type=RecordingTask.activity_type
    )
    mock_register.assert_called_once_with(
        client=db_client,
        simulation_id=SIMULATION_ID,
        spike_report_file=tmp_path / "spikes.h5",
        voltage_report_files=[tmp_path / "soma.h5"],
        lfp_report_files=[tmp_path / "LFP.h5"],
        name="Simulation result",
        description="Simulation result",
    )
    db_client.update_entity.assert_called_once_with(
        entity_id=ACTIVITY_ID,
        entity_type=RecordingTask.activity_type,
        attrs_or_entity={"generated_ids": [str(GENERATED_ID)]},
    )


def test_hooks_are_abstract(tmp_path):
    config = SimulationExecutionSingleConfig(
        idx=0, scan_output_root=tmp_path, coordinate_output_root=Path(tmp_path)
    )
    with pytest.raises(TypeError, match="abstract"):
        SimulationExecutionTask(config=config)
