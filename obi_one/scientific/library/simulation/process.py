import logging
import math
import os
from pathlib import Path

from obi_one.scientific.library.simulation.schemas import SimulationParameters, SimulationResults
from obi_one.types import SimulationBackend
from obi_one.utils.process import run_and_log

L = logging.getLogger(__name__)

# Path to cli that will be executed below
ENTRYPOINT_PATH = Path(__file__).parent.resolve() / "entrypoint.py"


def run_simulation(
    parameters: SimulationParameters,
    results_dir: Path,
    simulation_backend: SimulationBackend,
) -> SimulationResults:
    """Run simulation and collect outputs."""
    L.info("Running executable process...")
    match simulation_backend:
        case SimulationBackend.bluecellulab:
            _run_bluecellulab_simulation(
                parameters=parameters,
                simulation_entrypoint_path=ENTRYPOINT_PATH,
            )
        case SimulationBackend.neurodamus:
            _run_neurodamus_simulation(
                parameters=parameters,
            )
    return _collect_simulation_outputs(results_dir=results_dir)


def _run_bluecellulab_simulation(
    parameters: SimulationParameters,
    simulation_entrypoint_path: Path,
) -> None:
    number_of_mpi_processes = _get_number_of_mpi_processes(parameters.number_of_cells)

    run_and_log(
        [
            "mpiexec",
            "-n",
            str(number_of_mpi_processes),
            "python",
            str(simulation_entrypoint_path),
            "--config",
            str(parameters.config_file),
            "--libnrnmech-path",
            str(parameters.libmech_path),
            "--simulation-backend",
            str(SimulationBackend.bluecellulab),
            "--save-nwb",
        ]
    )


def _run_neurodamus_simulation(
    parameters: SimulationParameters,
) -> None:
    number_of_mpi_processes = _get_number_of_mpi_processes(parameters.number_of_cells)

    neurodamus_python = os.environ["NEURODAMUS_PYTHON"]

    run_and_log(
        [
            "mpirun",
            "--allow-run-as-root",
            "--use-hwthread-cpus",
            "-np",
            str(number_of_mpi_processes),
            "special",
            "-mpi",
            "-python",
            f"{neurodamus_python}/init.py",
            f"--configFile={parameters.config_file}",
        ],
        env=os.environ
        | {
            "CORENEURONLIB": str(parameters.libmech_path),
        },
    )


def _get_number_of_mpi_processes(num_cells: int) -> int:
    # Clamp between 1 and 4
    return min(max(math.floor(num_cells / 2), 1), 4)


def _collect_simulation_outputs(results_dir: Path) -> SimulationResults:
    spike_report_files = []
    voltage_report_files = []
    for filepath in list(results_dir.glob("*.h5")) + list(results_dir.glob(".nwb")):
        if filepath.name == "spikes.h5":
            spike_report_files.append(filepath)
        else:
            voltage_report_files.append(filepath)

    if len(spike_report_files) != 1:
        msg = f"Expected 1 spike report. Found {len(spike_report_files)}"
        raise RuntimeError(msg)

    return SimulationResults(
        spike_report_file=spike_report_files[0],
        voltage_report_files=voltage_report_files,
    )


def compile_mechanisms(
    *,
    output_dir: Path,
    mechanisms_dir: Path,
    simulation_backend: SimulationBackend,
) -> Path:

    match simulation_backend:
        case SimulationBackend.bluecellulab:
            return _compile_neuron_mechanisms(
                output_dir=output_dir,
                mechanisms_dir=mechanisms_dir,
            )
        case SimulationBackend.neurodamus:
            return _compile_neurodamus_mechanisms(
                output_dir=output_dir,
                mechanisms_dir=mechanisms_dir,
            )
        case _:
            msg = f"Unsupported simulation backend {simulation_backend}."
            raise RuntimeError(msg)


def _compile_neuron_mechanisms(*, output_dir: Path, mechanisms_dir: Path) -> Path:
    command = [
        "nrnivmodl",
        "-incflags",
        "-DDISABLE_REPORTINGLIB",
        str(mechanisms_dir),
    ]

    compilation_output = run_and_log(command, cwd=str(output_dir)).stdout  # ty:ignore[invalid-argument-type]

    L.debug(compilation_output)

    try:
        libnrnmech_path = next(output_dir.rglob("libnrnmech.so"))
    except StopIteration as e:
        msg = "Compiled mechanisms shared object libnrnmech.so was not found."
        raise RuntimeError(msg) from e

    return libnrnmech_path


def _compile_neurodamus_mechanisms(*, output_dir: Path, mechanisms_dir: Path) -> Path:
    command = [
        "nrnivmodl",
        "-coreneuron",
        str(mechanisms_dir),
    ]

    compilation_output = run_and_log(command, cwd=str(output_dir)).stdout  # ty:ignore[invalid-argument-type]

    L.debug(compilation_output)

    try:
        libcorenrnmech_path = next(output_dir.rglob("libcorenrnmech.so"))
    except StopIteration as e:
        msg = "Compiled mechanisms shared object libcorenrnmech.so was not found."
        raise RuntimeError(msg) from e

    return libcorenrnmech_path
