"""Subprocess logic for compiling mechanisms and running BlueRecording."""

from __future__ import annotations

import logging
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

L = logging.getLogger(__name__)


def run_bluerecording_write_weights(
    circuit_config: Path,
    electrode_json: Path,
    output_path: Path,
    nrnmech_lib_path: Path,
) -> Path:  # pragma: no cover
    """Run bluerecording write_weights as a subprocess.

    Args:
        circuit_config: Path to the SONATA circuit or simulation config.
        electrode_json: Path to the electrode JSON file.
        output_path: Path for the output weights H5 file.
        nrnmech_lib_path: Path to .so file that is placed in the environment in NRNMECH_LIB_PATH

    Returns:
        The output weights path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
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
