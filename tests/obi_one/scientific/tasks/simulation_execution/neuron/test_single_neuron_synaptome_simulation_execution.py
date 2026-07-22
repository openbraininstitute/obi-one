from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from obi_one.core.info import Info
from obi_one.scientific.from_id.circuit_from_id import MEModelWithSynapsesCircuitFromID
from obi_one.scientific.library.simulation.neuron.schemas import (
    NeurodamusMechanismBuild,
    NeurodamusSimulationParameters,
    SimulationResults,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model_with_synapses import (  # noqa: E501
    MEModelWithSynapsesCircuitSimulationScanConfig,
    MEModelWithSynapsesCircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.simulation_execution.neuron.single_neuron_synaptome_simulation_execution import (  # noqa: E501
    SingleNeuronSynaptomeSimulationExecutionSingleConfig,
    SingleNeuronSynaptomeSimulationExecutionTask,
)

_BASE = "obi_one.scientific.tasks.simulation_execution.neuron.base"
_CIRCUIT = "obi_one.scientific.tasks.simulation_execution.neuron.circuit_simulation_execution"


@pytest.fixture
def simulation_entity():
    entity = MagicMock()
    entity.id = UUID("12345678-1234-5678-1234-567812345678")
    entity.entity_id = UUID("87654321-4321-8765-4321-876543218765")
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
def db_client(simulation_entity):
    client = MagicMock()
    circuit_entity = MagicMock()
    circuit_entity.id = simulation_entity.entity_id
    client.get_entity.return_value = circuit_entity
    return client


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


@patch(f"{_BASE}.run_simulation")
@patch(f"{_BASE}.get_simulation_parameters")
@patch(f"{_BASE}.compile_mechanisms")
@patch(f"{_BASE}.stage_simulation")
@patch(f"{_CIRCUIT}.stage_circuit")
@patch(f"{_CIRCUIT}.db_sdk.get_identifiable")
@patch(f"{_BASE}.create_dir")
def test_execute_local_skips_registration(
    mock_create_dir,
    mock_get_identifiable,
    mock_stage_circuit,
    mock_stage_simulation,
    mock_compile,
    mock_get_params,
    mock_run_simulation,
    config,
    db_client,
    simulation_entity,
    tmp_path,
):
    mock_create_dir.side_effect = lambda path: path
    mock_get_identifiable.return_value = simulation_entity
    staged_circuit = MagicMock()
    staged_circuit.path = tmp_path / "circuit.json"
    staged_circuit.mechanisms_dir = tmp_path / "mechanisms"
    staged_circuit.directory = tmp_path / "circuit"
    mock_stage_circuit.return_value = staged_circuit
    mechanism_build = _neurodamus_mechanism_build(tmp_path)
    mock_compile.return_value = mechanism_build
    mock_stage_simulation.return_value = tmp_path / "sim_config.json"
    mock_get_params.return_value = NeurodamusSimulationParameters(
        number_of_cells=1,
        stop_time=100.0,
        config_file=tmp_path / "sim_config.json",
        mechanism_build=mechanism_build,
    )
    mock_run_simulation.return_value = SimulationResults(
        spike_report_file=tmp_path / "spikes.h5",
        voltage_report_files=[],
    )

    task = SingleNeuronSynaptomeSimulationExecutionTask(config=config)
    task.execute(db_client=db_client, execution_activity_id=None)

    mock_run_simulation.assert_called_once()
    db_client.update_entity.assert_not_called()
