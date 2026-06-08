import logging
import math
from pathlib import Path

from obi_one.scientific.library.memodel_circuit import MEModelCircuit
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
    _run_simulation_executable(
        parameters=parameters,
        simulation_backend=simulation_backend,
        simulation_entrypoint_path=ENTRYPOINT_PATH,
    )
    return _collect_simulation_outputs(results_dir=results_dir)


def _run_simulation_executable(
    parameters: SimulationParameters,
    simulation_backend: SimulationBackend,
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
            str(parameters.libnrnmech_path),
            "--simulation-backend",
            str(simulation_backend),
            "--save-nwb",
        ]
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


def compile_mechanisms(circuit: MEModelCircuit) -> Path:
    command = [
        "nrnivmodl",
        "-incflags",
        "-DDISABLE_REPORTINGLIB",
        circuit.mechanisms_dir.name,
    ]

    circuit_dir = circuit.directory.resolve()

    compilation_output = run_and_log(command, cwd=str(circuit_dir)).stdout  # ty:ignore[invalid-argument-type]

    L.debug(compilation_output)

    try:
        libnrnmech_path = next(circuit_dir.rglob("*nrnmech.so"))
    except StopIteration as e:
        msg = "Compiled mechanisms shared object *nrnmech.so was not found."
        raise RuntimeError(msg) from e

    return libnrnmech_path
