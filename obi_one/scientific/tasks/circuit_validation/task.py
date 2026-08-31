"""Circuit validation task.

Runs as an ECS task via the launch-system. The merged circuit is already
uploaded as a sonata_circuit directory asset. This task stages it (from EFS),
compiles MOD files, runs snap validation, and updates the entity status.
"""

from __future__ import annotations

import json
import logging
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import libsonata
from bluepysnap import circuit_validation
from entitysdk import Client, models
from entitysdk.staging.circuit import stage_circuit

from obi_one.scientific.library.circuit_id_mapping import validate_id_mapping_files
from obi_one.scientific.library.circuit_metrics import TYPES_OF_BIOPHYS_NODES

if TYPE_CHECKING:
    from uuid import UUID

    from bluepysnap import Circuit as SnapCircuitType
    from bluepysnap.nodes import NodePopulation

L = logging.getLogger(__name__)

_MOD_DECLARATION_PARTS = 2


def run_circuit_validation(
    *,
    db_client: Client,
    circuit_id: UUID,
) -> dict:
    """Validate a registered circuit.

    The circuit entity already has a sonata_circuit directory asset.
    This task stages it, compiles any MOD files, and runs snap validation.

    Args:
        db_client: EntitySDK client.
        circuit_id: The circuit entity ID.

    Returns:
        dict with keys: valid (bool), errors (list[str]), warnings (list[str])
    """
    circuit = db_client.get_entity(entity_id=circuit_id, entity_type=models.Circuit)

    with tempfile.TemporaryDirectory() as tmp_dir:
        staged_dir = Path(tmp_dir) / "circuit"
        staged_dir.mkdir()

        circuit_config_path = stage_circuit(db_client, model=circuit, output_dir=staged_dir)

        from bluepysnap import Circuit as SnapCircuit  # ruff: ignore[import-outside-top-level]

        try:
            snap_circuit = SnapCircuit(str(circuit_config_path))
        except Exception as e:  # ruff: ignore[blind-except]
            msg = f"Could not open circuit for validation: {e}"
            L.warning(msg)
            _update_lifecycle_status(db_client, circuit_id, "disqualified")
            return {"valid": False, "errors": [msg], "warnings": []}

        # Compile MOD files if present
        mod_dir = _find_mod_dir(snap_circuit)
        has_mods = bool(mod_dir and mod_dir.exists() and any(mod_dir.glob("*.mod")))
        if has_mods:
            try:
                _compile_mechanisms(mod_dir, staged_dir)
            except RuntimeError as e:
                _update_lifecycle_status(db_client, circuit_id, "disqualified")
                return {"valid": False, "errors": [str(e)], "warnings": []}

        fatal_errors: list[str] = []
        warning_messages: list[str] = []

        # Morphology path existence check (issue k)
        fatal_errors.extend(_validate_morphology_paths(snap_circuit))

        # Per-population HOC template existence check (issue l)
        fatal_errors.extend(_validate_emodel_paths(snap_circuit))

        # ID mapping file validity check (issue j)
        id_map_warnings = validate_id_mapping_files(circuit_config_path, snap_circuit)
        warning_messages.extend(id_map_warnings)

        # HOC template instantiation with bluecellulab
        hoc_errors = _validate_hoc_loading(
            snap_circuit,
            staged_dir,
            load_mods=has_mods,
            mod_dir=mod_dir if has_mods else None,
        )
        fatal_errors.extend(hoc_errors)

        # bluepysnap structural validation
        L.info("Running circuit validation on %s", circuit_config_path)
        snap_errors = circuit_validation.validate(str(circuit_config_path), skip_slow=False)
        fatal_errors.extend(str(e) for e in snap_errors if e.level == "FATAL")
        warning_messages.extend(str(e) for e in snap_errors if e.level == "WARNING")

        if fatal_errors:
            L.warning(
                "Circuit %s validation FAILED: %d fatal errors", circuit_id, len(fatal_errors)
            )
            _update_lifecycle_status(db_client, circuit_id, "disqualified")
            return {"valid": False, "errors": fatal_errors, "warnings": warning_messages}

        L.info("Circuit %s validation PASSED (%d warnings)", circuit_id, len(warning_messages))

        _update_lifecycle_status(db_client, circuit_id, "active")

        return {"valid": True, "errors": [], "warnings": warning_messages}


# ---------------------------------------------------------------------------
# Issue k: morphology path validation
# ---------------------------------------------------------------------------


def _validate_morphology_paths(circuit: SnapCircuitType) -> list[str]:
    """Verify that morphologies referenced by nodes actually exist.

    Uses bluepysnap to resolve morphology file paths for a sample of nodes in each
    biophysical population. This validates both file-based morphologies_dir and
    alternate_morphologies (H5 containers) transparently.
    """
    errors = []

    for pop_name in circuit.nodes.population_names:
        pop = circuit.nodes[pop_name]
        if getattr(pop, "type", None) not in TYPES_OF_BIOPHYS_NODES:
            continue

        # Sample node IDs to check morphology accessibility
        try:  # ruff: ignore[too-many-statements-in-try-clause]
            node_ids = pop.ids()
            if len(node_ids) == 0:
                continue
            # Sample up to 10 nodes evenly distributed
            sample_size = min(10, len(node_ids))
            step = max(1, len(node_ids) // sample_size)
            sample_ids = node_ids[::step][:sample_size]
        except Exception as e:  # ruff: ignore[blind-except]
            errors.append(f"Population '{pop_name}': could not retrieve node IDs: {e}")
            continue

        for node_id in sample_ids:
            try:
                filepath = pop.morph.get_filepath(node_id)
                if not Path(filepath).exists():
                    errors.append(f"Population '{pop_name}': morphology file not found: {filepath}")
                    break  # one missing file is enough to flag the population
            except Exception as e:  # ruff: ignore[blind-except]
                errors.append(
                    f"Population '{pop_name}': morphology not accessible for node {node_id}: {e}"
                )
                break

    return errors


# ---------------------------------------------------------------------------
# Issue l (task side): per-population emodel path validation
# ---------------------------------------------------------------------------


def _validate_emodel_paths(circuit: SnapCircuitType) -> list[str]:  # ruff: ignore[complex-structure]
    """Check that every biophysical neuron references an existing HOC template file.

    Uses bluepysnap so population-level and component-level
    ``biophysical_neuron_models_dir`` are resolved the same way as SNAP.
    """
    errors: list[str] = []

    for pop_name in circuit.nodes.population_names:
        pop = circuit.nodes[pop_name]
        if getattr(pop, "type", None) not in TYPES_OF_BIOPHYS_NODES:
            continue

        if "model_template" not in pop.property_names:
            errors.append(
                f"Population '{pop_name}': biophysical population is missing "
                "model_template property"
            )
            continue

        try:
            series = pop.get(properties="model_template")
            all_values = series.tolist()
            templates = [t for t in series.unique().tolist() if t]
            empty_count = sum(1 for t in all_values if not t)
        except Exception as e:  # ruff: ignore[blind-except]
            errors.append(f"Population '{pop_name}': could not read model_template: {e}")
            continue

        if empty_count:
            errors.append(
                f"Population '{pop_name}': {empty_count} biophysical neuron(s) "
                "have an empty model_template"
            )

        if not templates:
            errors.append(
                f"Population '{pop_name}': no model_template values found on biophysical neurons"
            )
            continue

        hoc_dir_str = pop.config.get("biophysical_neuron_models_dir")
        if not hoc_dir_str:
            errors.append(
                f"Population '{pop_name}': biophysical_neuron_models_dir is not configured"
            )
            continue
        hoc_dir = Path(hoc_dir_str)

        if not hoc_dir.exists():
            errors.append(
                f"Population '{pop_name}': biophysical_neuron_models_dir does not exist: {hoc_dir}"
            )
            continue

        for template_ref in templates:
            if ":" not in str(template_ref):
                errors.append(
                    f"Population '{pop_name}': model_template '{template_ref}' "
                    "is not in expected 'kind:name' form (e.g. 'hoc:CellA')"
                )
                continue
            kind, name = str(template_ref).split(":", 1)
            hoc_file = hoc_dir / f"{name}.{kind}"
            if not hoc_file.exists():
                errors.append(
                    f"Population '{pop_name}': HOC template '{hoc_file.name}'"
                    f" not found in {hoc_dir} (referenced by model_template "
                    f"'{template_ref}')"
                )

    return errors


# ---------------------------------------------------------------------------
# HOC loading validation (updated to use per-population hoc dirs)
# ---------------------------------------------------------------------------


def _mechanism_suffixes_from_mod_dir(mod_dir: Path) -> set[str]:
    """Collect mechanism names declared via SUFFIX / POINT_PROCESS in ``*.mod`` files."""
    suffixes: set[str] = set()
    for mod_file in sorted(mod_dir.glob("*.mod")):
        try:
            content = mod_file.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            L.warning("Could not read MOD file %s: %s", mod_file, e)
            continue
        for raw_line in content.splitlines():
            parts = raw_line.strip().split()
            if len(parts) >= _MOD_DECLARATION_PARTS and parts[0] in {"SUFFIX", "POINT_PROCESS"}:
                suffixes.add(parts[1])
    return suffixes


def _validate_hoc_loading(
    circuit: SnapCircuitType,
    working_dir: Path,
    *,
    load_mods: bool,
    mod_dir: Path | None = None,
) -> list[str]:
    """Validate HOC templates used by biophysical neurons with bluecellulab.

    For each unique ``model_template`` on biophysical populations:
    - require the HOC file to exist
    - resolve a morphology for a neuron that uses that template
    - if ``mod_dir`` is set, statically check ``insert`` mechanisms against MOD suffixes
      (avoids NEURON abort/segfault on missing mechanisms)
    - instantiate the template with bluecellulab
    """
    used = _collect_used_emodel_load_targets(circuit)
    if not used:
        return []

    expected_suffixes: set[str] | None = None
    if mod_dir is not None:
        expected_suffixes = _mechanism_suffixes_from_mod_dir(mod_dir)

    if load_mods:
        _load_compiled_mechanisms(working_dir)

    errors: list[str] = []
    for target in used:
        if not target["hoc_path"].exists():
            errors.append(
                f"Population '{target['pop_name']}': HOC template "
                f"'{target['hoc_path'].name}' not found for model_template "
                f"'{target['template_ref']}'"
            )
            continue
        if target["morph_path"] is None:
            errors.append(
                f"Population '{target['pop_name']}': could not resolve morphology "
                f"for model_template '{target['template_ref']}' "
                f"(needed to load-test HOC '{target['hoc_path'].name}')"
            )
            continue

        from obi_one.scientific.validations.emodels import (  # ruff: ignore[import-outside-top-level]
            bluecellulab_initializable,
            check_mechanisms,
        )

        if expected_suffixes is not None:
            try:
                check_mechanisms(target["hoc_path"], expected_suffixes)
            except ValueError as e:
                errors.append(
                    f"HOC template '{target['hoc_path'].name}' mechanism check failed: {e}"
                )
                L.warning(
                    "Mechanism check failed for HOC template %s: %s",
                    target["hoc_path"].name,
                    e,
                )
                continue

        try:
            bluecellulab_initializable(target["hoc_path"], target["morph_path"])
        except Exception as e:  # ruff: ignore[blind-except]
            errors.append(f"HOC template '{target['hoc_path'].name}' failed to instantiate: {e}")
            L.warning("Failed to instantiate HOC template %s: %s", target["hoc_path"].name, e)

    return errors


def _collect_used_emodel_load_targets(circuit: SnapCircuitType) -> list[dict]:
    """Collect unique used HOC templates with a morphology path for load-testing."""
    targets: list[dict] = []
    seen_templates: set[tuple[str, str]] = set()

    for pop_name in circuit.nodes.population_names:
        pop = circuit.nodes[pop_name]
        if getattr(pop, "type", None) not in TYPES_OF_BIOPHYS_NODES:
            continue
        if "model_template" not in pop.property_names:
            continue

        hoc_dir_str = pop.config.get("biophysical_neuron_models_dir")
        if not hoc_dir_str:
            continue
        hoc_dir = Path(hoc_dir_str)

        try:
            props = ["model_template"]
            if "morphology" in pop.property_names:
                props.append("morphology")
            df = pop.get(properties=props)
        except Exception as e:  # ruff: ignore[blind-except]
            L.warning("Could not read templates for population '%s': %s", pop_name, e)
            continue

        for node_id, row in df.iterrows():
            template_ref = row["model_template"]
            if not template_ref or ":" not in str(template_ref):
                continue
            key = (pop_name, str(template_ref))
            if key in seen_templates:
                continue
            seen_templates.add(key)

            kind, name = str(template_ref).split(":", 1)
            hoc_path = hoc_dir / f"{name}.{kind}"
            morph_path = _resolve_morphology_path(pop, node_id)
            targets.append(
                {
                    "pop_name": pop_name,
                    "template_ref": str(template_ref),
                    "hoc_path": hoc_path,
                    "morph_path": morph_path,
                    "node_id": node_id,
                }
            )

    return targets


def _collect_hoc_files(circuit: SnapCircuitType) -> list[Path]:
    """Collect HOC files from each population's resolved biophysical_neuron_models_dir."""
    hoc_dirs: list[Path] = []
    for pop_name in circuit.nodes.population_names:
        pop = circuit.nodes[pop_name]
        if getattr(pop, "type", None) not in TYPES_OF_BIOPHYS_NODES:
            continue
        dir_str = pop.config.get("biophysical_neuron_models_dir")
        if not dir_str:
            continue
        hoc_dir = Path(dir_str)
        if hoc_dir.exists() and hoc_dir not in hoc_dirs:
            hoc_dirs.append(hoc_dir)

    return [f for d in hoc_dirs for f in d.glob("*.hoc")]


def _load_compiled_mechanisms(working_dir: Path) -> None:
    """Load compiled mechanisms from the working directory if available.

    ``nrnivmodl`` writes architecture-specific shared libraries under
    ``x86_64/`` or ``arm64/`` (``libnrnmech.so`` on Linux, ``libnrnmech.dylib``
    on macOS). Prefer NEURON's ``load_mechanisms``, which resolves those paths.
    """
    x86_dir = working_dir / "x86_64"
    arm64_dir = working_dir / "arm64"
    if not x86_dir.exists() and not arm64_dir.exists():
        return

    import neuron  # ruff: ignore[import-outside-top-level]

    neuron.load_mechanisms(str(working_dir))


def _resolve_morphology_path(pop: NodePopulation, node_id: int | str) -> Path | None:
    """Resolve an on-disk morphology path for a node via bluepysnap MorphHelper."""
    try:
        morph_path = Path(pop.morph.get_filepath(node_id))
        if morph_path.exists():
            return morph_path
    except Exception as e:  # ruff: ignore[blind-except]
        L.debug("get_filepath(%s) failed: %s", node_id, e)

    for ext in ("swc", "asc", "h5"):
        try:
            morph_path = Path(pop.morph.get_filepath(node_id, extension=ext))
            if morph_path.exists():
                return morph_path
        except Exception as e:  # ruff: ignore[blind-except]
            L.debug("get_filepath(%s, %s) failed: %s", node_id, ext, e)
            continue
    return None


def _find_morphology_for_template(template_name: str, circuit: SnapCircuitType) -> Path | None:
    """Find a morphology that uses the given HOC template via the nodes file."""
    try:  # ruff: ignore[too-many-statements-in-try-clause]
        for pop_name in circuit.nodes.population_names:
            pop = circuit.nodes[pop_name]
            if getattr(pop, "type", None) not in TYPES_OF_BIOPHYS_NODES:
                continue
            if "model_template" not in pop.property_names:
                continue
            if "morphology" not in pop.property_names:
                continue
            df = pop.get(properties=["model_template", "morphology"])
            match = df[df["model_template"].str.contains(template_name, na=False)]
            if match.empty:
                continue
            node_id = match.index[0]
            morph_path = _resolve_morphology_path(pop, node_id)
            if morph_path is not None:
                return morph_path
    except Exception as e:  # ruff: ignore[blind-except]
        L.warning("Could not find morphology for template '%s': %s", template_name, e)
    return None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _update_lifecycle_status(db_client: Client, circuit_id: UUID, status: str) -> None:
    """Update the circuit's lifecycle_status (entitysdk >= 0.18.0)."""
    try:
        db_client.update_entity(
            entity_id=circuit_id,
            entity_type=models.Circuit,
            attrs_or_entity={"lifecycle_status": status},
        )
        L.info("Circuit %s lifecycle_status -> %s", circuit_id, status)
    except Exception:  # ruff: ignore[blind-except]
        L.warning("Failed to update lifecycle_status for circuit %s", circuit_id, exc_info=True)


def _find_mod_dir(circuit: SnapCircuitType) -> Path | None:
    """Find a mechanisms directory via SNAP's resolved per-population ``mechanisms_dir``.

    SNAP resolves both global ``components.mechanisms_dir`` and population-level
    overrides into ``population.config``. Some circuits point ``mechanisms_dir`` at
    the circuit root while ``.mod`` files live in a ``mod/`` subdirectory.
    """
    for pop_name in circuit.nodes.population_names:
        mech = circuit.nodes[pop_name].config.get("mechanisms_dir")
        if not mech:
            continue
        mech_path = Path(mech)
        if mech_path.exists() and any(mech_path.glob("*.mod")):
            return mech_path
        nested = mech_path / "mod"
        if nested.exists() and any(nested.glob("*.mod")):
            return nested
    return None


def _compile_mechanisms(mod_dir: Path, working_dir: Path) -> None:
    """Compile MOD files with nrnivmodl. Raises on failure."""
    L.info("Compiling MOD files from %s", mod_dir)
    try:
        subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            ["nrnivmodl", "-incflags", "-DDISABLE_REPORTINGLIB", str(mod_dir)],  # ruff: ignore[start-process-with-partial-path]
            check=True,
            capture_output=True,
            cwd=str(working_dir),
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace") if e.stderr else ""
        msg = f"MOD compilation failed: {stderr[:500]}"
        raise RuntimeError(msg) from e
    L.info("MOD compilation successful")
