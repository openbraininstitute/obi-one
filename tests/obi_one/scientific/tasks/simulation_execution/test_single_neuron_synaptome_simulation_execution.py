from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from obi_one.core.info import Info
from obi_one.scientific.from_id.circuit_from_id import MEModelWithSynapsesCircuitFromID
from obi_one.scientific.library.simulation.schemas import (
    NeurodamusMechanismBuild,
    NeurodamusSimulationParameters,
    SimulationResults,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model_with_synapses import (  # noqa: E501
    MEModelWithSynapsesCircuitSimulationScanConfig,
    MEModelWithSynapsesCircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.simulation_execution.single_neuron_synaptome_simulation_execution import (  # noqa: E501
    SingleNeuronSynaptomeSimulationExecutionSingleConfig,
    SingleNeuronSynaptomeSimulationExecutionTask,
)
from obi_one.types import SimulationBackend

_BASE = "obi_one.scientific.tasks.simulation_execution.base"
_SYNAPTOME = (
    "obi_one.scientific.tasks.simulation_execution.single_neuron_synaptome_simulation_execution"
)


@pytest.fixture
def simulation_entity():
    entity = MagicMock()
    entity.id = UUID("12345678-1234-5678-1234-567812345678")
    return entity


@pytest.fixture
def generation_config(tmp_path, simulation_entity):
    config = MEModelWithSynapsesCircuitSimulationSingleConfig(
        info=Info(campaign_name="test", campaign_description="test"),
        initialize=MEModelWithSynapsesCircuitSimulationScanConfig.Initialize(
            circuit=MEModelWithSynapsesCircuitFromID(id_str="circuit-id"),
        ),
        idx=0,
        scan_output_root=tmp_path,
        coordinate_output_root=tmp_path / "coord",
    )
    config.set_single_entity(simulation_entity)
    return config


@pytest.fixture
def config(tmp_path, simulation_entity):
    task_config = SingleNeuronSynaptomeSimulationExecutionSingleConfig(
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


@patch(f"{_SYNAPTOME}.SingleNeuronSynaptomeSimulationExecutionTask.get_generation_single_config")
@patch(f"{_BASE}.run_simulation")
@patch(f"{_BASE}.get_simulation_parameters")
@patch(f"{_BASE}.stage_simulation")
@patch(f"{_BASE}.compile_mechanisms")
@patch(f"{_SYNAPTOME}.stage_memodel_with_synapses_as_circuit")
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

    task = SingleNeuronSynaptomeSimulationExecutionTask(config=config)
    task.execute(db_client=db_client, execution_activity_id=None)

    mock_stage_circuit.assert_called_once()
    mock_compile.assert_called_once_with(
        mechanisms_dir=staged_circuit.mechanisms_dir.resolve(),
        output_dir=staged_circuit.directory.resolve(),
        simulation_backend=SimulationBackend.neurodamus,
    )
    db_client.get_entity.assert_not_called()
    db_client.update_entity.assert_not_called()
