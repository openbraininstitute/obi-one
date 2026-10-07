"""Subprocess logic for compiling mechanisms and running BlueRecording."""

from __future__ import annotations

import logging
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

L = logging.getLogger(__name__)

# write_weights splits the cells between its MPI processes. These are the CPU counts a
# launch-system job can have, so the job is given one CPU per process.
MPI_PROCESS_COUNTS = (1, 2, 4, 8, 16)
CELLS_PER_MPI_PROCESS = 100


def get_number_of_mpi_processes(n_cells: int) -> int:
    """Number of MPI processes to run write_weights with for a circuit of n_cells cells."""
    return next(
        (n for n in MPI_PROCESS_COUNTS if n * CELLS_PER_MPI_PROCESS >= n_cells),
        MPI_PROCESS_COUNTS[-1],
    )


def run_bluerecording_write_weights(
    circuit_config: Path,
    electrode_json: Path,
    output_path: Path,
    nrnmech_lib_path: Path,
    number_of_mpi_processes: int,
) -> Path:  # pragma: no cover
    """Run bluerecording write_weights under MPI as a subprocess.

    Args:
        circuit_config: Path to the SONATA circuit or simulation config.
        electrode_json: Path to the electrode JSON file.
        output_path: Path for the output weights H5 file.
        nrnmech_lib_path: Path to .so file that is placed in the environment in NRNMECH_LIB_PATH
        number_of_mpi_processes: Number of MPI processes, at most the number of CPUs.

    Returns:
        The output weights path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "mpirun",
        "--use-hwthread-cpus",
        "-np",
        str(number_of_mpi_processes),
        "bluerecording",
        "write_weights",
        str(circuit_config),
        str(electrode_json),
        str(output_path),
    ]

    L.info("Running bluerecording: %s", " ".join(cmd))

    # Output is not captured, so bluerecording's progress reaches the job log as it runs.
    # ENVIRONMENT=BATCH turns off neurodamus's colours.
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        cmd,
        check=False,
        env={
            **os.environ,
            "NRNMECH_LIB_PATH": str(nrnmech_lib_path),
            "PYTHONUNBUFFERED": "1",
            "ENVIRONMENT": "BATCH",
        },
    )

    if result.returncode != 0:
        msg = (
            f"bluerecording write_weights failed (exit {result.returncode}); see its output above."
        )
        raise RuntimeError(msg)

    return output_path
