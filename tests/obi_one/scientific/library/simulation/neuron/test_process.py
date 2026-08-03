from unittest.mock import patch

import pytest

from obi_one.scientific.library.simulation.neuron import process as test_module
from obi_one.scientific.library.simulation.neuron.schemas import (
    BluecellulabSimulationParameters,
    NeurodamusMechanismBuild,
    NeurodamusSimulationParameters,
    NeuronMechanismBuild,
    SimulationResults,
)
from obi_one.types import SimulationBackend


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("dummy")
    return path


def _neuron_mechanism_build(tmp_path):
    return NeuronMechanismBuild(libnrnmech_path=_touch(tmp_path / "libnrnmech.so"))


def _neurodamus_mechanism_build(tmp_path):
    return NeurodamusMechanismBuild(
        libnrnmech_path=_touch(tmp_path / "libnrnmech.so"),
        libcorenrnmech_path=_touch(tmp_path / "libcorenrnmech.so"),
        special_binary_path=_touch(tmp_path / "special"),
    )


def test_get_number_of_mpi_processes():
    assert test_module._get_number_of_mpi_processes(0) == 1
    assert test_module._get_number_of_mpi_processes(1) == 1
    assert test_module._get_number_of_mpi_processes(2) == 1
    assert test_module._get_number_of_mpi_processes(5) == 2
    assert test_module._get_number_of_mpi_processes(10) == 4  # clamped at 4


def test_collect_simulation_outputs(tmp_path):
    spike_file = tmp_path / "spikes.h5"
    spike_file.write_text("spikes")
    voltage_file = tmp_path / "voltage.h5"
    voltage_file.write_text("voltage")

    results = test_module._collect_simulation_outputs(tmp_path)
    assert isinstance(results, SimulationResults)
    assert results.spike_report_file == spike_file
    assert voltage_file in results.voltage_report_files

    spike_file.unlink()
    with pytest.raises(RuntimeError):
        test_module._collect_simulation_outputs(tmp_path)


@patch("obi_one.scientific.library.simulation.neuron.process._run_bluecellulab_simulation")
@patch("obi_one.scientific.library.simulation.neuron.process._collect_simulation_outputs")
def test_run_simulation_bluecellulab(mock_collect, mock_run, tmp_path):
    mechanism_build = _neuron_mechanism_build(tmp_path)
    parameters = BluecellulabSimulationParameters(
        number_of_cells=4,
        config_file=tmp_path / "config.json",
        stop_time=0.1,
        mechanism_build=mechanism_build,
    )
    backend = SimulationBackend.bluecellulab
    expected_results = SimulationResults(
        spike_report_file=tmp_path / "spikes.h5", voltage_report_files=[]
    )
    mock_collect.return_value = expected_results

    results = test_module.run_simulation(parameters, tmp_path, backend)

    mock_run.assert_called_once_with(
        parameters=parameters,
        simulation_entrypoint_path=test_module.ENTRYPOINT_PATH,
    )
    mock_collect.assert_called_once_with(results_dir=tmp_path)
    assert results == expected_results


@patch("obi_one.scientific.library.simulation.neuron.process._run_neurodamus_simulation")
@patch("obi_one.scientific.library.simulation.neuron.process._collect_simulation_outputs")
def test_run_simulation_neurodamus(mock_collect, mock_run, tmp_path):
    mechanism_build = _neurodamus_mechanism_build(tmp_path)
    parameters = NeurodamusSimulationParameters(
        number_of_cells=4,
        config_file=tmp_path / "config.json",
        stop_time=0.1,
        mechanism_build=mechanism_build,
    )
    backend = SimulationBackend.neurodamus
    expected_results = SimulationResults(
        spike_report_file=tmp_path / "spikes.h5", voltage_report_files=[]
    )
    mock_collect.return_value = expected_results

    results = test_module.run_simulation(parameters, tmp_path, backend)

    mock_run.assert_called_once_with(parameters=parameters)
    mock_collect.assert_called_once_with(results_dir=tmp_path)
    assert results == expected_results


@patch("obi_one.scientific.library.simulation.neuron.process.run_and_log")
def test_run_bluecellulab_simulation(mock_run_and_log, tmp_path):
    mechanism_build = _neuron_mechanism_build(tmp_path)
    parameters = BluecellulabSimulationParameters(
        number_of_cells=4,
        config_file=tmp_path / "config.json",
        stop_time=0.1,
        mechanism_build=mechanism_build,
    )
    test_module._run_bluecellulab_simulation(
        parameters,
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
        str(mechanism_build.libnrnmech_path),
        "--simulation-backend",
        "bluecellulab",
        "--save-nwb",
    ]


@patch("obi_one.scientific.library.simulation.neuron.process.run_and_log")
def test_run_neurodamus_simulation(mock_run_and_log, monkeypatch, tmp_path):
    monkeypatch.setenv("NEURODAMUS_PYTHON", "/opt/neurodamus")
    mechanism_build = _neurodamus_mechanism_build(tmp_path)
    parameters = NeurodamusSimulationParameters(
        number_of_cells=4,
        config_file=tmp_path / "config.json",
        stop_time=0.1,
        mechanism_build=mechanism_build,
    )

    test_module._run_neurodamus_simulation(parameters)

    mock_run_and_log.assert_called_once()
    call_cmd = mock_run_and_log.call_args[0][0]
    assert call_cmd == [
        "mpirun",
        "--use-hwthread-cpus",
        "-np",
        "2",
        str(mechanism_build.special_binary_path),
        "-mpi",
        "-python",
        "/opt/neurodamus/init.py",
        f"--configFile={parameters.config_file}",
    ]
    assert mock_run_and_log.call_args[1]["env"]["NRNMECH_LIB_PATH"] == str(
        mechanism_build.libnrnmech_path
    )
    assert mock_run_and_log.call_args[1]["env"]["CORENEURONLIB"] == str(
        mechanism_build.libcorenrnmech_path
    )


@patch("obi_one.scientific.library.simulation.neuron.process.run_and_log")
def test_compile_neuron_mechanisms(mock_run_and_log, tmp_path):
    mech_dir = tmp_path / "mech"
    mech_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    mock_run_and_log.return_value.stdout = "compilation done"

    so_file = output_dir / "x86_64" / "libnrnmech.so"
    so_file.parent.mkdir(parents=True)
    so_file.write_text("dummy")

    mechanism_build = test_module.compile_mechanisms(
        output_dir=output_dir,
        mechanisms_dir=mech_dir,
        simulation_backend=SimulationBackend.bluecellulab,
    )

    assert isinstance(mechanism_build, NeuronMechanismBuild)
    assert mechanism_build.libnrnmech_path == so_file
    mock_run_and_log.assert_called_once_with(
        [
            "nrnivmodl",
            "-incflags",
            "-DDISABLE_REPORTINGLIB",
            str(mech_dir),
        ],
        cwd=str(output_dir),
    )


@patch("obi_one.scientific.library.simulation.neuron.process.find_file")
@patch("obi_one.scientific.library.simulation.neuron.process.run_and_log")
def test_compile_neurodamus_mechanisms(mock_run_and_log, mock_find_file, tmp_path):
    mech_dir = tmp_path / "mech"
    mech_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    mock_run_and_log.return_value.stdout = "compilation done"

    special_path = _touch(output_dir / "special")
    libnrnmech_path = _touch(output_dir / "libnrnmech.so")
    libcorenrnmech_path = _touch(output_dir / "libcorenrnmech.so")
    mock_find_file.side_effect = [special_path, libnrnmech_path, libcorenrnmech_path]

    mechanism_build = test_module.compile_mechanisms(
        output_dir=output_dir,
        mechanisms_dir=mech_dir,
        simulation_backend=SimulationBackend.neurodamus,
    )

    assert isinstance(mechanism_build, NeurodamusMechanismBuild)
    assert mechanism_build.special_binary_path == special_path
    assert mechanism_build.libnrnmech_path == libnrnmech_path
    assert mechanism_build.libcorenrnmech_path == libcorenrnmech_path
    mock_run_and_log.assert_called_once_with(
        [
            "neurodamus-compile-mods",
            "--input-dir",
            str(mech_dir),
            "--output-dir",
            str(output_dir),
            "--with-internal-mods",
            "--simulator",
            "coreneuron",
        ],
        cwd=str(output_dir),
    )


def test_compile_mechanisms_unsupported_backend(tmp_path):
    with pytest.raises(RuntimeError, match="Unsupported simulation backend"):
        test_module.compile_mechanisms(
            output_dir=tmp_path,
            mechanisms_dir=tmp_path / "mech",
            simulation_backend="unsupported",  # ty:ignore[invalid-argument-type]
        )
