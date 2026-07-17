"""Subprocess logic for compiling mechanisms and running BlueRecording."""

from __future__ import annotations

import json
import logging
import os
import subprocess  # noqa: S404
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

L = logging.getLogger(__name__)


def compile_mechanisms(circuit_config_path: Path, output_dir: Path) -> dict[str, str]:
    """Compile NMODL mechanisms for a circuit via neurodamus-compile-mods.

    Compiles the circuit's mod files plus neurodamus internal mods with
    ``-DDISABLE_REPORTINGLIB`` (stubs out SonataReport so libsonatareport
    headers are not needed).

    Args:
        circuit_config_path: Path to a SONATA circuit configuration file.
        output_dir: Directory for compiled mechanism artifacts.

    Returns:
        Environment dict containing ``NRNMECH_LIB_PATH`` (and optionally
        ``CORENEURONLIB``, ``SPECIALS_PATH``).
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "neurodamus-compile-mods",
        "--circuit-config",
        str(circuit_config_path),
        "--with-internal-mods",
        "--output-dir",
        str(output_dir),
        "--output-type",
        "json",
        "--incflags",
        "-DDISABLE_REPORTINGLIB",
    ]

    L.info("Compiling mechanisms: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603

    if result.returncode != 0:
        msg = f"neurodamus-compile-mods failed (exit {result.returncode}):\n{result.stderr}"
        raise RuntimeError(msg)

    return json.loads(result.stdout)


def write_electrode_json(
    electrode_locations: dict,
    calculation_method: str,
    output_path: Path,
) -> Path:
    """Write electrode positions to a JSON file for the bluerecording CLI.

    Builds global positions from each block's ``get_global_electrode_xyz_locations()``
    and writes them in the format expected by ``Electrode.from_json``.

    Args:
        electrode_locations: Dict of electrode location blocks (name -> block).
        calculation_method: One of "PointSource", "LineSource", "ObjectiveCSD".
        output_path: Path to write the JSON file.

    Returns:
        The output path.
    """
    electrodes = []
    for block_name, block in electrode_locations.items():
        for i, (x, y, z) in enumerate(block.get_global_electrode_xyz_locations()):
            electrodes.append(
                {
                    "name": f"{block_name}_electrode_{i}",
                    "x": float(x),
                    "y": float(y),
                    "z": float(z),
                    "type": calculation_method,
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(electrodes, f, indent=2)

    L.info("Wrote %d electrodes to %s", len(electrodes), output_path)
    return output_path


def run_bluerecording_write_weights(
    circuit_config: Path,
    electrode_json: Path,
    output_path: Path,
    env: dict[str, str],
) -> Path:
    """Run bluerecording write_weights as a subprocess.

    Args:
        circuit_config: Path to the SONATA circuit or simulation config.
        electrode_json: Path to the electrode JSON file.
        output_path: Path for the output weights H5 file.
        env: Environment dict (should include NRNMECH_LIB_PATH).

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
        "--with-neurite-type",
    ]

    L.info("Running bluerecording: %s", " ".join(cmd))

    result = subprocess.run(  # noqa: S603
        cmd, capture_output=True, text=True, check=False, env={**os.environ, **env}
    )

    if result.returncode != 0:
        L.error("bluerecording stderr: %s", result.stderr)
        msg = f"bluerecording write_weights failed (exit {result.returncode}):\n{result.stderr}"
        raise RuntimeError(msg)

    if result.stdout:
        L.debug("bluerecording stdout: %s", result.stdout.strip())

    return output_path
