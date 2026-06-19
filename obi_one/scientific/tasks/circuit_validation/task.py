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
        has_mods = bool(mod_dir and mod_dir.exists() and any(mod_dir.glob("*.mod")))
        if has_mods:
            _compile_mechanisms(mod_dir, staged_dir)

        # Validate HOC templates load correctly with NEURON
        hoc_errors = _validate_hoc_loading(circuit_config_path, staged_dir, load_mods=has_mods)

        # Run snap validation
        L.info("Running circuit validation on %s", circuit_config_path)
        errors = circuit_validation.validate(str(circuit_config_path), skip_slow=False)

        fatal_errors = hoc_errors + [str(e) for e in errors if e.level == "FATAL"]
        warning_errors = [str(e) for e in errors if e.level == "WARNING"]

        if fatal_errors:
            L.warning(
                "Circuit %s validation FAILED: %d fatal errors", circuit_id, len(fatal_errors)
            )
            _update_readiness_status(db_client, circuit_id, "failed")
            return {"valid": False, "errors": fatal_errors, "warnings": warning_errors}

        L.info("Circuit %s validation PASSED (%d warnings)", circuit_id, len(warning_errors))
        _update_readiness_status(db_client, circuit_id, "active")
        return {"valid": True, "errors": [], "warnings": warning_errors}


def _validate_hoc_loading(
    circuit_config_path: Path, working_dir: Path, *, load_mods: bool
) -> list[str]:
    """Validate HOC templates by instantiating them with bluecellulab.

    Uses Aurélien's approach: fully instantiate each HOC template with a morphology
    from the circuit to verify it works end-to-end.
    """
    config = libsonata.CircuitConfig.from_file(str(circuit_config_path))
    cfg = json.loads(config.expanded_json)
    hoc_dir_str = cfg.get("components", {}).get("biophysical_neuron_models_dir", "")
    if not hoc_dir_str:
        return []

    hoc_dir = Path(hoc_dir_str) if Path(hoc_dir_str).is_absolute() else working_dir / hoc_dir_str
    if not hoc_dir.exists():
        return []

    hoc_files = list(hoc_dir.glob("*.hoc"))
    if not hoc_files:
        return []

    # Load compiled mechanisms
    if load_mods:
        x86_dir = working_dir / "x86_64"
        arm64_dir = working_dir / "arm64"
        mech_dir = x86_dir if x86_dir.exists() else arm64_dir if arm64_dir.exists() else None
        if mech_dir:
            from neuron import h  # noqa: PLC0415

            h.nrn_load_dll(str(mech_dir / "special.so"))

    # Find a morphology to test with
    morph_path = _find_morphology_for_template(hoc_files[0].stem, circuit_config_path)
    if not morph_path:
        L.warning("No morphology found for HOC validation — falling back to load_file check")
        return _validate_hoc_load_only(hoc_files)

    # Instantiate each HOC template with bluecellulab
    from bluecellulab import Cell  # noqa: PLC0415
    from bluecellulab.circuit.circuit_access.definition import EmodelProperties  # noqa: PLC0415

    emodel_properties = EmodelProperties(holding_current=0.0, threshold_current=0.0)
    errors = []

    for hoc_path in hoc_files:
        L.info("Validating HOC template with bluecellulab: %s", hoc_path.name)
        morph_path = _find_morphology_for_template(hoc_path.stem, circuit_config_path)
        if not morph_path:
            L.warning("No morphology found for template '%s' — skipping", hoc_path.name)
            continue
        try:
            _ = Cell(
                template_path=str(hoc_path),
                morphology_path=str(morph_path),
                template_format="v6",
                emodel_properties=emodel_properties,
            )
        except Exception as e:  # noqa: BLE001
            errors.append(f"HOC template '{hoc_path.name}' failed to instantiate: {e}")
            L.warning("Failed to instantiate HOC template %s: %s", hoc_path.name, e)

    return errors


def _find_morphology_for_template(template_name: str, circuit_config_path: Path) -> Path | None:
    """Find a morphology that uses the given HOC template via the nodes file.

    Reads the circuit with bluepysnap, finds a node with matching model_template,
    and returns its morphology path.
    """
    from bluepysnap import Circuit  # noqa: PLC0415

    try:
        circuit = Circuit(str(circuit_config_path))
        for pop_name in circuit.nodes.population_names:
            pop = circuit.nodes[pop_name]
            if "model_template" not in pop.property_names:
                continue
            df = pop.get(properties=["model_template", "morphology"])
            match = df[df["model_template"].str.contains(template_name, na=False)]
            if match.empty:
                continue
            node_id = match.index[0]
            for ext in ("swc", "asc", "h5"):
                try:
                    morph_path = pop.morph.get_morphology_path(node_id, extension=ext)
                    if Path(morph_path).exists():
                        return Path(morph_path)
                except Exception:  # noqa: BLE001, S112
                    continue
    except Exception as e:  # noqa: BLE001
        L.warning("Could not find morphology for template '%s': %s", template_name, e)
    return None


def _validate_hoc_load_only(hoc_files: list[Path]) -> list[str]:
    """Fallback: just check NEURON can parse the HOC file (no morphology available)."""
    from bluecellulab.importer import import_hoc  # noqa: PLC0415
    from neuron import h as neuron  # noqa: PLC0415

    import_hoc(neuron)
    errors = []
    for hoc_path in hoc_files:
        result = neuron.load_file(str(hoc_path))
        if not result:
            errors.append(f"HOC template failed to load: '{hoc_path.name}'")
    return errors


def _update_readiness_status(db_client: Client, circuit_id: UUID, status: str) -> None:
    try:
        db_client.update_entity(
            entity_id=circuit_id,
            entity_type=models.Circuit,
            attrs_or_entity={"readiness_status": status},
        )
        L.info("Circuit %s readiness_status -> %s", circuit_id, status)
    except Exception:  # noqa: BLE001
        L.warning("Failed to update readiness_status for circuit %s", circuit_id, exc_info=True)


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
