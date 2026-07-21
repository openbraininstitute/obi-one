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


def compile_mechanisms(
    circuit_config_path: Path, output_dir: Path
) -> dict[str, str]:  # pragma: no cover
    """Compile NMODL mechanisms for a circuit via neurodamus-compile-mods.

    Discovers mod files from the circuit's ``mechanisms_dir`` (via
    ``--circuit-config``). If that's empty/unset, falls back to a ``mod/``
    directory next to the circuit config (common convention for bundled
    circuits). Compiles with ``-DDISABLE_REPORTINGLIB`` to stub out
    SonataReport (no libsonatareport headers needed).

    Args:
        circuit_config_path: Path to a SONATA circuit configuration file.
        output_dir: Directory for compiled mechanism artifacts.

    Returns:
        Environment dict containing ``NRNMECH_LIB_PATH`` (and optionally
        ``CORENEURONLIB``, ``SPECIALS_PATH``). Empty dict if no mods found.
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
        "--incflags=-DDISABLE_REPORTINGLIB",
    ]

    # Fallback: look for a 'mod/' directory next to the circuit config.
    mod_dir = circuit_config_path.parent / "mod"
    has_fallback_mods = mod_dir.is_dir() and any(mod_dir.glob("*.mod"))
    if has_fallback_mods:
        cmd.extend(["--input-dir", str(mod_dir)])
        L.warning(
            "Circuit mechanisms_dir is empty; falling back to '%s' (%d .mod files).",
            mod_dir,
            len(list(mod_dir.glob("*.mod"))),
        )

    L.info("Compiling mechanisms: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603

    if result.returncode != 0:
        if "No mod files selected" in result.stderr:
            L.warning(
                "No mod files found to compile. "
                "Checked mechanisms_dir from circuit config and fallback '%s'. "
                "Relying on pre-existing NRNMECH_LIB_PATH.",
                mod_dir,
            )
            return {}
        msg = f"neurodamus-compile-mods failed (exit {result.returncode}):\n{result.stderr}"
        raise RuntimeError(msg)

    return json.loads(result.stdout)


def write_electrode_json(
    electrode_locations: dict,
    calculation_method: str,
    output_path: Path,
) -> Path:  # pragma: no cover
    """Write electrode positions to a JSON file for the bluerecording CLI.

    Builds global positions from each block's ``get_global_electrode_xyz_locations()``
    and writes them using ``Electrode.to_json`` from bluerecording.

    Args:
        electrode_locations: Dict of electrode location blocks (name -> block).
        calculation_method: One of "PointSource", "LineSource", "ObjectiveCSD".
        output_path: Path to write the JSON file.

    Returns:
        The output path.
    """
    import numpy as np  # noqa: PLC0415
    from bluerecording.electrodes import (  # noqa: PLC0415 # ty:ignore[unresolved-import]
        Electrode,
        ElectrodeType,
    )

    electrodes = [
        Electrode(
            name=f"{block_name}_electrode_{i}",
            position=np.array([x, y, z], dtype=float),
            type=ElectrodeType(calculation_method),
        )
        for block_name, block in electrode_locations.items()
        for i, (x, y, z) in enumerate(block.get_global_electrode_xyz_locations())
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    Electrode.to_json(electrodes, str(output_path))

    L.info("Wrote %d electrodes to %s", len(electrodes), output_path)
    return output_path


def run_bluerecording_write_weights(
    circuit_config: Path,
    electrode_json: Path,
    output_path: Path,
    env: dict[str, str],
) -> Path:  # pragma: no cover
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
    ]

    L.info("Running bluerecording: %s", " ".join(cmd))

    # Use the compiled library exclusively — it contains both circuit mods and
    # neurodamus internals compiled together, avoiding duplicate mechanism errors.
    subprocess_env = {**os.environ, **env}

    result = subprocess.run(  # noqa: S603
        cmd, capture_output=True, text=True, check=False, env=subprocess_env
    )

    if result.returncode != 0:
        L.error("bluerecording stderr: %s", result.stderr)
        msg = f"bluerecording write_weights failed (exit {result.returncode}):\n{result.stderr}"
        raise RuntimeError(msg)

    if result.stdout:
        L.debug("bluerecording stdout: %s", result.stdout.strip())

    return output_path
