from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from obi_one.core.info import Info
from obi_one.scientific.blocks.ion_channel_model import IonChannelModelWithConductance
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.scientific.library.simulation.schemas import SimulationParameters, SimulationResults
from obi_one.scientific.tasks import ion_channel_model_simulation_execution as test_module
from obi_one.scientific.tasks.generate_simulations.config.ion_channel_models import (
    IonChannelModelSimulationScanConfig,
    IonChannelModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.ion_channel_model_simulation_execution import (
    IonChannelModelSimulationExecutionSingleConfig,
    IonChannelModelSimulationExecutionTask,
)


@pytest.fixture
def simulation_entity():
    entity = MagicMock()
    entity.id = UUID("12345678-1234-5678-1234-567812345678")
    return entity


@pytest.fixture
def generation_config(tmp_path, simulation_entity):
    config = IonChannelModelSimulationSingleConfig(
        info=Info(campaign_name="test", campaign_description="test"),
        initialize=IonChannelModelSimulationScanConfig.Initialize(),
        ion_channel_models={
            "ic1": IonChannelModelWithConductance(
                ion_channel_model=IonChannelModelFromID(id_str="test-id"),
                conductance=1.0,
            )
        },
        idx=0,
        scan_output_root=tmp_path,
        coordinate_output_root=tmp_path / "coord",
    )
    config.set_single_entity(simulation_entity)
    return config


@pytest.fixture
def config(tmp_path, simulation_entity):
    config = IonChannelModelSimulationExecutionSingleConfig(
        idx=0,
        scan_output_root=tmp_path,
        coordinate_output_root=tmp_path / "coord",
    )
    config.set_single_entity(simulation_entity)
    return config


@pytest.fixture
def db_client():
    return MagicMock()


@patch(
    "obi_one.scientific.tasks.ion_channel_model_simulation_execution.IonChannelModelSimulationExecutionTask.get_generation_single_config"
)
@patch("obi_one.scientific.tasks.ion_channel_model_simulation_execution.run_simulation")
@patch("obi_one.scientific.tasks.ion_channel_model_simulation_execution.get_simulation_parameters")
@patch("obi_one.scientific.tasks.ion_channel_model_simulation_execution.stage_simulation")
@patch("obi_one.scientific.tasks.ion_channel_model_simulation_execution.compile_mechanisms")
@patch(
    "obi_one.scientific.tasks.ion_channel_model_simulation_execution.stage_ion_channel_models_as_circuit"
)
@patch("obi_one.scientific.tasks.ion_channel_model_simulation_execution.create_dir")
def test_execute_local_does_not_register(
    mock_create_dir,
    mock_stage_circuit,
    mock_compile,
    mock_stage_sim,
    mock_get_params,
    mock_run_simulation,
    mock_get_generation_config,
    config,
    generation_config,
    db_client,
    tmp_path,
):
    mock_create_dir.side_effect = lambda p: p
    mock_get_generation_config.return_value = generation_config
    staged_circuit = MagicMock()
    staged_circuit.path = tmp_path / "circuit.json"
    mock_stage_circuit.return_value = staged_circuit
    mock_compile.return_value = tmp_path / "libnrnmech.so"
    db_client.get_entity.return_value = config.single_entity
    mock_stage_sim.return_value = tmp_path / "sim_config.json"
    mock_get_params.return_value = SimulationParameters(
        number_of_cells=1,
        stop_time=100.0,
        config_file=tmp_path / "config.json",
        libnrnmech_path=tmp_path / "libnrnmech.so",
    )
    mock_run_simulation.return_value = SimulationResults(
        spike_report_file=tmp_path / "spikes.h5",
        voltage_report_files=[],
    )

    task = IonChannelModelSimulationExecutionTask(config=config)
    task.execute(db_client=db_client, execution_activity_id=None)

    mock_stage_circuit.assert_called_once()
    mock_compile.assert_called_once_with(staged_circuit)
    db_client.get_entity.assert_not_called()
    mock_stage_sim.assert_called_once()
    mock_get_params.assert_called_once()
    mock_run_simulation.assert_called_once()
    db_client.update_entity.assert_not_called()


@patch(
    "obi_one.scientific.tasks.ion_channel_model_simulation_execution.IonChannelModelSimulationExecutionTask.get_generation_single_config"
)
@patch(
    "obi_one.scientific.tasks.ion_channel_model_simulation_execution.register_simulation_results"
)
@patch("obi_one.scientific.tasks.ion_channel_model_simulation_execution.run_simulation")
@patch("obi_one.scientific.tasks.ion_channel_model_simulation_execution.get_simulation_parameters")
@patch("obi_one.scientific.tasks.ion_channel_model_simulation_execution.stage_simulation")
@patch("obi_one.scientific.tasks.ion_channel_model_simulation_execution.compile_mechanisms")
@patch(
    "obi_one.scientific.tasks.ion_channel_model_simulation_execution.stage_ion_channel_models_as_circuit"
)
@patch("obi_one.scientific.tasks.ion_channel_model_simulation_execution.create_dir")
def test_execute_tracked_registers_and_updates_activity(
    mock_create_dir,
    mock_stage_circuit,
    mock_compile,
    mock_stage_sim,
    mock_get_params,
    mock_run_simulation,
    mock_register,
    mock_get_generation_config,
    config,
    generation_config,
    db_client,
    tmp_path,
):
    mock_create_dir.side_effect = lambda p: p
    mock_get_generation_config.return_value = generation_config
    staged_circuit = MagicMock()
    staged_circuit.path = tmp_path / "circuit.json"
    mock_stage_circuit.return_value = staged_circuit
    mock_compile.return_value = tmp_path / "libnrnmech.so"
    execution_activity = MagicMock()
    execution_activity.id = "act-456"
    db_client.get_entity.side_effect = [execution_activity, config.single_entity]
    mock_stage_sim.return_value = tmp_path / "sim_config.json"
    mock_get_params.return_value = SimulationParameters(
        number_of_cells=1,
        stop_time=100.0,
        config_file=tmp_path / "config.json",
        libnrnmech_path=tmp_path / "libnrnmech.so",
    )
    sim_results = SimulationResults(
        spike_report_file=tmp_path / "spikes.h5",
        voltage_report_files=[],
    )
    mock_run_simulation.return_value = sim_results
    generated_entity = MagicMock()
    generated_entity.id = "gen-789"
    mock_register.return_value = generated_entity

    task = IonChannelModelSimulationExecutionTask(config=config)
    task.execute(db_client=db_client, execution_activity_id="act-456")

    assert db_client.get_entity.call_count == 1
    db_client.get_entity.assert_called_once_with(
        entity_id="act-456",
        entity_type=test_module.IonChannelModelSimulationExecutionTask.activity_type,
    )
    mock_register.assert_called_once()
    call_kw = mock_register.call_args[1]
    assert call_kw["client"] == db_client
    assert call_kw["simulation_results"] == sim_results
    assert call_kw["simulation_metadata"].simulation_id == config.single_entity.id
    db_client.update_entity.assert_called_once_with(
        entity_id="act-456",
        entity_type=test_module.IonChannelModelSimulationExecutionTask.activity_type,
        attrs_or_entity={"generated_ids": ["gen-789"]},
    )
