from unittest.mock import Mock, patch

import pytest

from obi_one.scientific.library.simulation import process as test_module
from obi_one.scientific.library.simulation.schemas import SimulationParameters, SimulationResults
from obi_one.types import SimulationBackend


def test_get_number_of_mpi_processes():
    assert test_module._get_number_of_mpi_processes(0) == 1
    assert test_module._get_number_of_mpi_processes(1) == 1
    assert test_module._get_number_of_mpi_processes(2) == 1
    assert test_module._get_number_of_mpi_processes(5) == 2
    assert test_module._get_number_of_mpi_processes(10) == 4  # clamped at 4


def test_collect_simulation_outputs(tmp_path):
    # Create dummy files
    spike_file = tmp_path / "spikes.h5"
    spike_file.write_text("spikes")
    voltage_file = tmp_path / "voltage.h5"
    voltage_file.write_text("voltage")

    results = test_module._collect_simulation_outputs(tmp_path)
    assert isinstance(results, SimulationResults)
    assert results.spike_report_file == spike_file
    assert voltage_file in results.voltage_report_files

    # Test failure if no spike file
    spike_file.unlink()
    with pytest.raises(RuntimeError):
        test_module._collect_simulation_outputs(tmp_path)


@patch("obi_one.scientific.library.simulation.process._run_simulation_executable")
@patch("obi_one.scientific.library.simulation.process._collect_simulation_outputs")
def test_run_simulation(mock_collect, mock_run, tmp_path):
    parameters = SimulationParameters(
        number_of_cells=4,
        config_file=tmp_path / "config.json",
        libnrnmech_path=tmp_path / "libnrnmech.so",
        stop_time=0.1,
    )
    backend = SimulationBackend.bluecellulab
    expected_results = SimulationResults(
        spike_report_file=tmp_path / "spikes.h5", voltage_report_files=[]
    )
    mock_collect.return_value = expected_results

    results = test_module.run_simulation(parameters, tmp_path, backend)

    mock_run.assert_called_once_with(
        parameters=parameters,
        simulation_backend=backend,
        simulation_entrypoint_path=test_module.ENTRYPOINT_PATH,
    )
    mock_collect.assert_called_once_with(results_dir=tmp_path)
    assert results == expected_results


@patch("obi_one.scientific.library.simulation.process.run_and_log")
def test_run_simulation_executable(mock_run_and_log, tmp_path):
    parameters = SimulationParameters(
        number_of_cells=4,
        config_file=tmp_path / "config.json",
        libnrnmech_path=tmp_path / "libnrnmech.so",
        stop_time=0.1,
    )
    test_module._run_simulation_executable(
        parameters,
        SimulationBackend.bluecellulab,
        tmp_path / "entry.py",
    )
    mock_run_and_log.assert_called_once()
    call_cmd = mock_run_and_log.call_args[0][0]
    assert call_cmd == [
        "mpiexec",
        "-n",
        "2",
        "python",
        str(tmp_path / "entry.py"),
        "--config",
        str(parameters.config_file),
        "--libnrnmech-path",
        str(parameters.libnrnmech_path),
        "--simulation-backend",
        "bluecellulab",
        "--save-nwb",
    ]


@patch("obi_one.scientific.library.simulation.process.run_and_log")
def test_compile_mechanisms(mock_run_and_log, tmp_path):
    mech_dir = tmp_path / "mech"
    mech_dir.mkdir()
    circuit_dir = tmp_path / "circuit"
    circuit_dir.mkdir()
    circuit_config_path = circuit_dir / "circuit_config.json"
    circuit_config_path.touch()
    circuit = Mock()
    circuit.directory = circuit_dir
    circuit.mechanisms_dir = mech_dir

    mock_run_and_log.return_value.stdout = "compilation done"

    so_file = circuit_dir / "libnrnmech.so"
    so_file.write_text("dummy")

    lib_path = test_module.compile_mechanisms(circuit)
    assert lib_path == so_file
