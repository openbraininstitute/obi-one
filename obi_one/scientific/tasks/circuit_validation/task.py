"""Circuit validation task.

Runs as an ECS task via the launch-system. The merged circuit is already
uploaded as a sonata_circuit directory asset. This task stages it (from EFS),
compiles MOD files, runs snap validation, and updates the entity status.
"""

import json
import logging
import subprocess  # noqa: S404
import tempfile
from pathlib import Path
from uuid import UUID

import libsonata
from bluepysnap import circuit_validation
from entitysdk import Client, models
from entitysdk.staging.circuit import stage_circuit

L = logging.getLogger(__name__)


def run_circuit_validation(
    *,
    db_client: Client,
    circuit_id: UUID,
) -> dict:
    """Validate a customized circuit.

    The circuit entity already has a merged sonata_circuit directory asset.
    This task stages it, compiles any MOD files, and runs snap validation.

    Args:
        db_client: EntitySDK client.
        circuit_id: The customized circuit entity ID.

    Returns:
        dict with keys: valid (bool), errors (list[str]), warnings (list[str])
    """
    circuit = db_client.get_entity(entity_id=circuit_id, entity_type=models.Circuit)

    with tempfile.TemporaryDirectory() as tmp_dir:
        staged_dir = Path(tmp_dir) / "circuit"
        staged_dir.mkdir()

        # Stage the merged circuit from EFS
        circuit_config_path = stage_circuit(db_client, model=circuit, output_dir=staged_dir)

        # Compile MOD files if present
        mod_dir = _find_mod_dir(circuit_config_path)
        if mod_dir and mod_dir.exists() and any(mod_dir.glob("*.mod")):
            _compile_mechanisms(mod_dir, staged_dir)

        # Run snap validation
        L.info("Running circuit validation on %s", circuit_config_path)
        errors = circuit_validation.validate(str(circuit_config_path), skip_slow=False)

        fatal_errors = [str(e) for e in errors if e.level == "FATAL"]
        warning_errors = [str(e) for e in errors if e.level == "WARNING"]

        if fatal_errors:
            L.warning(
                "Circuit %s validation FAILED: %d fatal errors", circuit_id, len(fatal_errors)
            )
            # TODO: Update entity status to "draft" with errors once entitycore supports it
            return {"valid": False, "errors": fatal_errors, "warnings": warning_errors}

        L.info("Circuit %s validation PASSED (%d warnings)", circuit_id, len(warning_errors))
        # TODO: Update entity status to "active" once entitycore supports it
        return {"valid": True, "errors": [], "warnings": warning_errors}


def _find_mod_dir(circuit_config_path: Path) -> Path | None:
    """Find the mechanisms directory from circuit_config.json using libsonata."""
    config = libsonata.CircuitConfig.from_file(str(circuit_config_path))
    cfg = json.loads(config.expanded_json)
    mod_dir = cfg.get("components", {}).get("mechanisms_dir", "")
    if mod_dir:
        return Path(mod_dir)
    return None


def _compile_mechanisms(mod_dir: Path, working_dir: Path) -> None:
    """Compile MOD files with nrnivmodl. Raises on failure."""
    L.info("Compiling MOD files from %s", mod_dir)
    try:
        subprocess.run(  # noqa: S603
            ["nrnivmodl", "-incflags", "-DDISABLE_REPORTINGLIB", str(mod_dir)],  # noqa: S607
            check=True,
            capture_output=True,
            cwd=str(working_dir),
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace") if e.stderr else ""
        msg = f"MOD compilation failed: {stderr[:500]}"
        raise RuntimeError(msg) from e
    L.info("MOD compilation successful")
