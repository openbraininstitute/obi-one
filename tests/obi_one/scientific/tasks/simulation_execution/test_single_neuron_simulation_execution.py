from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from obi_one.core.info import Info
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.simulation.schemas import (
    NeurodamusMechanismBuild,
    NeurodamusSimulationParameters,
    SimulationResults,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (
    MEModelSimulationScanConfig,
    MEModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.simulation_execution import (
    single_neuron_simulation_execution as test_module,
)
from obi_one.scientific.tasks.simulation_execution.single_neuron_simulation_execution import (
    SingleNeuronSimulationExecutionSingleConfig,
    SingleNeuronSimulationExecutionTask,
)
from obi_one.types import SimulationBackend

_BASE = "obi_one.scientific.tasks.simulation_execution.base"
_SINGLE_NEURON = "obi_one.scientific.tasks.simulation_execution.single_neuron_simulation_execution"


@pytest.fixture
def simulation_entity():
    entity = MagicMock()
    entity.id = UUID("12345678-1234-5678-1234-567812345678")
    return entity


@pytest.fixture
def generation_config(tmp_path, simulation_entity):
    config = MEModelSimulationSingleConfig(
        info=Info(campaign_name="test", campaign_description="test"),
        initialize=MEModelSimulationScanConfig.Initialize(
            circuit=MEModelFromID(id_str="memodel-id"),
        ),
        idx=0,
        scan_output_root=tmp_path,
        coordinate_output_root=tmp_path / "coord",
    )
    config.set_single_entity(simulation_entity)
    return config


@pytest.fixture
def config(tmp_path, simulation_entity):
    task_config = SingleNeuronSimulationExecutionSingleConfig(
        idx=0,
        scan_output_root=tmp_path,
        coordinate_output_root=tmp_path / "coord",
    )
    task_config.set_single_entity(simulation_entity)
    return task_config


@pytest.fixture
def db_client():
    return MagicMock()


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("dummy")
    return path


def _neurodamus_mechanism_build(tmp_path):
    return NeurodamusMechanismBuild(
        libnrnmech_path=_touch(tmp_path / "libnrnmech.so"),
        libcorenrnmech_path=_touch(tmp_path / "libcorenrnmech.so"),
        special_binary_path=_touch(tmp_path / "special"),
    )


@patch(f"{_SINGLE_NEURON}.SingleNeuronSimulationExecutionTask.get_generation_single_config")
@patch(f"{_BASE}.run_simulation")
@patch(f"{_BASE}.get_simulation_parameters")
@patch(f"{_BASE}.stage_simulation")
@patch(f"{_BASE}.compile_mechanisms")
@patch(f"{_SINGLE_NEURON}.stage_memodel_as_circuit")
@patch(f"{_BASE}.create_dir")
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
    mock_create_dir.side_effect = lambda path: path
    mock_get_generation_config.return_value = generation_config
    staged_circuit = MagicMock()
    staged_circuit.path = tmp_path / "circuit.json"
    staged_circuit.mechanisms_dir = tmp_path / "mechanisms"
    staged_circuit.directory = tmp_path / "circuit"
    mock_stage_circuit.return_value = staged_circuit
    mechanism_build = _neurodamus_mechanism_build(tmp_path)
    mock_compile.return_value = mechanism_build
    mock_stage_sim.return_value = tmp_path / "sim_config.json"
    mock_get_params.return_value = NeurodamusSimulationParameters(
        number_of_cells=1,
        stop_time=100.0,
        config_file=tmp_path / "config.json",
        mechanism_build=mechanism_build,
    )
    mock_run_simulation.return_value = SimulationResults(
        spike_report_file=tmp_path / "spikes.h5",
        voltage_report_files=[],
    )

    task = SingleNeuronSimulationExecutionTask(config=config)
    task.execute(db_client=db_client, execution_activity_id=None)

    mock_stage_circuit.assert_called_once()
    mock_compile.assert_called_once_with(
        mechanisms_dir=staged_circuit.mechanisms_dir.resolve(),
        output_dir=staged_circuit.directory.resolve(),
        simulation_backend=SimulationBackend.neurodamus,
    )
    db_client.get_entity.assert_not_called()
    db_client.update_entity.assert_not_called()


@patch(f"{_SINGLE_NEURON}.SingleNeuronSimulationExecutionTask.get_generation_single_config")
@patch(f"{_BASE}.register_simulation_results")
@patch(f"{_BASE}.run_simulation")
@patch(f"{_BASE}.get_simulation_parameters")
@patch(f"{_BASE}.stage_simulation")
@patch(f"{_BASE}.compile_mechanisms")
@patch(f"{_SINGLE_NEURON}.stage_memodel_as_circuit")
@patch(f"{_BASE}.create_dir")
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
    mock_create_dir.side_effect = lambda path: path
    mock_get_generation_config.return_value = generation_config
    staged_circuit = MagicMock()
    staged_circuit.path = tmp_path / "circuit.json"
    staged_circuit.mechanisms_dir = tmp_path / "mechanisms"
    staged_circuit.directory = tmp_path / "circuit"
    mock_stage_circuit.return_value = staged_circuit
    mechanism_build = _neurodamus_mechanism_build(tmp_path)
    mock_compile.return_value = mechanism_build
    execution_activity = MagicMock()
    execution_activity.id = "act-456"
    db_client.get_entity.return_value = execution_activity
    mock_stage_sim.return_value = tmp_path / "sim_config.json"
    sim_results = SimulationResults(
        spike_report_file=tmp_path / "spikes.h5",
        voltage_report_files=[],
    )
    mock_get_params.return_value = NeurodamusSimulationParameters(
        number_of_cells=1,
        stop_time=100.0,
        config_file=tmp_path / "config.json",
        mechanism_build=mechanism_build,
    )
    mock_run_simulation.return_value = sim_results
    generated_entity = MagicMock()
    generated_entity.id = "gen-789"
    mock_register.return_value = generated_entity

    task = SingleNeuronSimulationExecutionTask(config=config)
    task.execute(db_client=db_client, execution_activity_id="act-456")

    db_client.get_entity.assert_called_once_with(
        entity_id="act-456",
        entity_type=test_module.SingleNeuronSimulationExecutionTask.activity_type,
    )
    mock_register.assert_called_once()
    db_client.update_entity.assert_called_once_with(
        entity_id="act-456",
        entity_type=test_module.SingleNeuronSimulationExecutionTask.activity_type,
        attrs_or_entity={"generated_ids": ["gen-789"]},
    )


@patch(f"{_SINGLE_NEURON}.deserialize_obi_object_from_json_data")
@patch(f"{_SINGLE_NEURON}.db_sdk.select_json_asset_content")
def test_get_generation_single_config(
    mock_select_json, mock_deserialize, config, generation_config
):
    mock_select_json.return_value = {"type": "memodel"}
    mock_deserialize.return_value = generation_config

    task = SingleNeuronSimulationExecutionTask(config=config)
    result = task.get_generation_single_config(db_client=MagicMock())

    assert result is generation_config
    mock_select_json.assert_called_once()


@patch(f"{_SINGLE_NEURON}.deserialize_obi_object_from_json_data")
@patch(f"{_SINGLE_NEURON}.db_sdk.select_json_asset_content")
def test_get_generation_single_config_wrong_type(mock_select_json, mock_deserialize, config):
    mock_select_json.return_value = {"type": "other"}
    mock_deserialize.return_value = MagicMock()

    task = SingleNeuronSimulationExecutionTask(config=config)
    with pytest.raises(test_module.OBIONEError, match="Expected MEModelSimulationSingleConfig"):
        task.get_generation_single_config(db_client=MagicMock())
