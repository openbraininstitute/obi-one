"""Circuit validation task.

Runs as an ECS task via the launch-system. The merged circuit is already
uploaded as a sonata_circuit directory asset. This task stages it (from EFS),
compiles MOD files, runs snap validation, and updates the entity status.
"""

from __future__ import annotations

import json
import logging
import subprocess  # noqa: S404
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import h5py
import libsonata
from bluepysnap import circuit_validation
from entitysdk import Client, models
from entitysdk.staging.circuit import stage_circuit

if TYPE_CHECKING:
    import types
    from uuid import UUID

    from bluepysnap import Circuit as SnapCircuitType
    from bluepysnap.nodes import NodePopulation

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

        circuit_config_path = stage_circuit(db_client, model=circuit, output_dir=staged_dir)

        # Compile MOD files if present
        mod_dir = _find_mod_dir(circuit_config_path)
        has_mods = bool(mod_dir and mod_dir.exists() and any(mod_dir.glob("*.mod")))
        if has_mods:
            _compile_mechanisms(mod_dir, staged_dir)

        fatal_errors: list[str] = []
        warning_messages: list[str] = []

        # Morphology path existence check (issue k)
        fatal_errors.extend(_validate_morphology_paths(circuit_config_path))

        # Per-population HOC template existence check (issue l)
        fatal_errors.extend(_validate_emodel_paths(circuit_config_path))

        # ID mapping file validity check (issue j)
        id_map_warnings = _validate_id_mapping_files(circuit_config_path)
        warning_messages.extend(id_map_warnings)

        # HOC template instantiation with bluecellulab
        hoc_errors = _validate_hoc_loading(circuit_config_path, staged_dir, load_mods=has_mods)
        fatal_errors.extend(hoc_errors)

        # bluepysnap structural validation
        L.info("Running circuit validation on %s", circuit_config_path)
        snap_errors = circuit_validation.validate(str(circuit_config_path), skip_slow=False)
        fatal_errors.extend(str(e) for e in snap_errors if e.level == "FATAL")
        warning_messages.extend(str(e) for e in snap_errors if e.level == "WARNING")

        # Subset checks: morphologies and emodels must exist in parent
        if circuit.root_circuit_id:
            subset_errors = _check_content_subset_of_parent(
                db_client, circuit.root_circuit_id, circuit_config_path
            )
            fatal_errors.extend(subset_errors)

            # Node columns check: only model_template/etype should differ from parent
            col_warnings = _check_node_columns_unchanged(
                db_client, circuit.root_circuit_id, circuit_config_path
            )
            warning_messages.extend(col_warnings)

        if fatal_errors:
            L.warning(
                "Circuit %s validation FAILED: %d fatal errors", circuit_id, len(fatal_errors)
            )
            _update_readiness_status(db_client, circuit_id, "failed")
            return {"valid": False, "errors": fatal_errors, "warnings": warning_messages}

        L.info("Circuit %s validation PASSED (%d warnings)", circuit_id, len(warning_messages))

        _recompute_dynamic_params(circuit_config_path)

        _update_readiness_status(db_client, circuit_id, "active")
        return {"valid": True, "errors": [], "warnings": warning_messages}


# ---------------------------------------------------------------------------
# Issue k: morphology path validation
# ---------------------------------------------------------------------------


def _validate_morphology_paths(circuit_config_path: Path) -> list[str]:
    """Verify that the morphologies_dir referenced in the circuit config exists on disk.

    Resolves per-population morphologies_dir (takes precedence over the component-level
    default). Fails if the directory is missing or not a directory.
    """
    config = libsonata.CircuitConfig.from_file(str(circuit_config_path))
    cfg = json.loads(config.expanded_json)
    component_morph_dir = cfg.get("components", {}).get("morphologies_dir", "")
    errors = []

    for entry in cfg.get("networks", {}).get("nodes", []):
        for pop_name, pop_cfg in entry.get("populations", {}).items():
            if pop_cfg.get("type") == "virtual":
                continue

            morph_dir_str = pop_cfg.get("morphologies_dir", "") or component_morph_dir
            if not morph_dir_str:
                continue

            morph_dir = Path(morph_dir_str)
            if not morph_dir.exists():
                errors.append(
                    f"Population '{pop_name}': morphologies_dir does not exist: {morph_dir}"
                )
            elif not morph_dir.is_dir():
                errors.append(
                    f"Population '{pop_name}': morphologies_dir is not a directory: {morph_dir}"
                )

    return errors


# ---------------------------------------------------------------------------
# Issue l (task side): per-population emodel path validation
# ---------------------------------------------------------------------------


def _validate_emodel_paths(circuit_config_path: Path) -> list[str]:
    """Check that all HOC template files referenced by biophysical populations exist.

    Resolves biophysical_neuron_models_dir per population (population-level override
    takes precedence over the component-level default).
    """
    config = libsonata.CircuitConfig.from_file(str(circuit_config_path))
    cfg = json.loads(config.expanded_json)
    component_hoc_dir = cfg.get("components", {}).get("biophysical_neuron_models_dir", "")
    errors = []

    for entry in cfg.get("networks", {}).get("nodes", []):
        nodes_file_str = entry.get("nodes_file", "")
        for pop_name, pop_cfg in entry.get("populations", {}).items():
            if pop_cfg.get("type") == "virtual":
                continue

            hoc_dir_str = pop_cfg.get("biophysical_neuron_models_dir", "") or component_hoc_dir
            if not hoc_dir_str:
                continue
            hoc_dir = Path(hoc_dir_str)

            if not hoc_dir.exists():
                errors.append(
                    f"Population '{pop_name}': biophysical_neuron_models_dir does not exist:"
                    f" {hoc_dir}"
                )
                continue

            if not nodes_file_str:
                continue
            templates = _read_model_templates(nodes_file_str, pop_name)
            for template_ref in templates:
                if ":" not in template_ref:
                    continue
                kind, name = template_ref.split(":", 1)
                hoc_file = hoc_dir / f"{name}.{kind}"
                if not hoc_file.exists():
                    errors.append(
                        f"Population '{pop_name}': HOC template '{hoc_file.name}'"
                        f" not found in {hoc_dir}"
                    )

    return errors


def _read_model_templates(nodes_file: str, pop_name: str) -> set[str]:
    """Read unique model_template values for a population from its H5 file."""
    try:
        with h5py.File(nodes_file, "r") as f:
            if "nodes" not in f or pop_name not in f["nodes"]:
                return set()
            group = f["nodes"][pop_name].get("0", f["nodes"][pop_name])
            if "model_template" not in group:
                return set()
            raw = group["model_template"][:]
            return {t.decode() if isinstance(t, bytes) else str(t) for t in raw}
    except Exception as e:  # noqa: BLE001
        L.warning("Could not read model_template from '%s' (pop '%s'): %s", nodes_file, pop_name, e)
        return set()


# ---------------------------------------------------------------------------
# Issue j: ID mapping file validity
# ---------------------------------------------------------------------------


def _validate_id_mapping_files(circuit_config_path: Path) -> list[str]:
    """Validate the brainbuilder id_mapping.json if present.

    id_mapping.json is produced by brainbuilder's subcircuit extraction and referenced at
    components.provenance.id_mapping in circuit_config.json. Its format per population is:
        { "new_id": [...], "parent_id": [...], "original_id": [...],
          "parent_name": "...", "original_name": "..." }

    When nodes are replaced (different count or IDs), the new_id values may exceed the
    population size and the mapping becomes invalid. We warn and remove the file if stale
    (removal only if it is a symlink, i.e. inherited from the parent circuit).

    Returns a list of warning messages.
    """
    config = libsonata.CircuitConfig.from_file(str(circuit_config_path))
    cfg = json.loads(config.expanded_json)

    id_mapping_rel = cfg.get("components", {}).get("provenance", {}).get("id_mapping")
    if not id_mapping_rel:
        return []

    id_mapping_path = circuit_config_path.parent / id_mapping_rel
    if not id_mapping_path.exists():
        return []

    try:
        mapping: dict = json.loads(id_mapping_path.read_text())
    except Exception as e:  # noqa: BLE001
        return [f"id_mapping.json: could not parse: {e}"]

    pop_sizes = _get_population_sizes(cfg)
    stale_populations = _find_stale_populations(mapping, pop_sizes)

    if not stale_populations:
        return []

    detail = "; ".join(stale_populations)
    msg = f"id_mapping.json is stale after nodes replacement ({detail})"
    if id_mapping_path.is_symlink():
        id_mapping_path.unlink()
        msg += " — file removed from the circuit (regenerate with brainbuilder if needed)"
    else:
        msg += (
            " — file was not removed (not a parent symlink);"
            " regenerate with brainbuilder or remove manually"
        )
    L.warning(msg)
    return [msg]


def _get_population_sizes(cfg: dict) -> dict[str, int]:
    """Build per-population node count from the H5 files referenced in the config."""
    pop_sizes: dict[str, int] = {}
    for entry in cfg.get("networks", {}).get("nodes", []):
        nodes_file = entry.get("nodes_file", "")
        if not nodes_file:
            continue
        try:
            with h5py.File(nodes_file, "r") as f:
                for pname in f.get("nodes", {}):
                    pop_group = f["nodes"][pname]
                    if "node_type_id" in pop_group:
                        pop_sizes[pname] = pop_group["node_type_id"].shape[0]
        except Exception as e:  # noqa: BLE001
            L.warning("Could not read population sizes from '%s': %s", nodes_file, e)
    return pop_sizes


def _find_stale_populations(mapping: dict, pop_sizes: dict[str, int]) -> list[str]:
    """Identify populations where id_mapping new_id exceeds the population size."""
    stale: list[str] = []
    for pop_name, entry in mapping.items():
        if not isinstance(entry, dict) or "new_id" not in entry:
            continue
        new_ids = entry["new_id"]
        if not new_ids:
            continue
        max_new_id = max(new_ids)
        pop_size = pop_sizes.get(pop_name)
        if pop_size is not None and max_new_id >= pop_size:
            stale.append(
                f"'{pop_name}': max new_id={max_new_id} but population has {pop_size} nodes"
            )
    return stale


# ---------------------------------------------------------------------------
# HOC loading validation (updated to use per-population hoc dirs)
# ---------------------------------------------------------------------------


def _validate_hoc_loading(
    circuit_config_path: Path, working_dir: Path, *, load_mods: bool
) -> list[str]:
    """Validate HOC templates by instantiating them with bluecellulab."""
    config = libsonata.CircuitConfig.from_file(str(circuit_config_path))
    cfg = json.loads(config.expanded_json)

    all_hoc_files = _collect_hoc_files(cfg, working_dir)
    if not all_hoc_files:
        return []

    if load_mods:
        _load_compiled_mechanisms(working_dir)

    from bluecellulab import Cell  # noqa: PLC0415
    from bluecellulab.circuit.circuit_access.definition import EmodelProperties  # noqa: PLC0415

    emodel_properties = EmodelProperties(holding_current=0.0, threshold_current=0.0)
    errors = []

    for hoc_path in all_hoc_files:
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


def _collect_hoc_files(cfg: dict, working_dir: Path) -> list[Path]:
    """Collect all HOC files from per-population biophysical_neuron_models_dir."""
    component_hoc_dir = cfg.get("components", {}).get("biophysical_neuron_models_dir", "")

    hoc_dirs: list[Path] = []
    for entry in cfg.get("networks", {}).get("nodes", []):
        for pop_cfg in entry.get("populations", {}).values():
            if pop_cfg.get("type") == "virtual":
                continue
            dir_str = pop_cfg.get("biophysical_neuron_models_dir", "") or component_hoc_dir
            if not dir_str:
                continue
            hoc_dir = Path(dir_str) if Path(dir_str).is_absolute() else working_dir / dir_str
            if hoc_dir.exists() and hoc_dir not in hoc_dirs:
                hoc_dirs.append(hoc_dir)

    return [f for d in hoc_dirs for f in d.glob("*.hoc")]


def _load_compiled_mechanisms(working_dir: Path) -> None:
    """Load compiled mechanisms from the working directory if available."""
    x86_dir = working_dir / "x86_64"
    arm64_dir = working_dir / "arm64"
    mech_dir = x86_dir if x86_dir.exists() else arm64_dir if arm64_dir.exists() else None
    if mech_dir:
        from neuron import h  # noqa: PLC0415

        h.nrn_load_dll(str(mech_dir / "special.so"))


def _find_morphology_for_template(template_name: str, circuit_config_path: Path) -> Path | None:
    """Find a morphology that uses the given HOC template via the nodes file."""
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


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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


def _recompute_dynamic_params(circuit_config_path: Path) -> None:
    """Recompute dynamic parameters (holding/threshold current) for ME-models in the circuit."""
    from bluepysnap import Circuit  # noqa: PLC0415

    try:
        circuit = Circuit(str(circuit_config_path))
    except Exception as e:  # noqa: BLE001
        L.warning("Could not load circuit for dynamic params recomputation: %s", e)
        return

    for pop_name in circuit.nodes.population_names:
        pop = circuit.nodes[pop_name]
        if "model_template" not in pop.property_names:
            continue
        if pop.type == "virtual":
            continue

        L.info("Recomputing dynamic params for population '%s'", pop_name)
        updated_holding, updated_threshold = _compute_population_dynamics(pop)

        if updated_holding:
            _write_dynamics_to_h5(circuit_config_path, pop_name, updated_holding, updated_threshold)

    L.info("Dynamic params recomputation complete")


def _compute_population_dynamics(
    pop: NodePopulation,
) -> tuple[dict[int, float], dict[int, float]]:
    """Compute holding/threshold currents for all nodes in a population."""
    from bluecellulab.tools import (  # noqa: PLC0415
        compute_memodel_properties_v2,  # ty:ignore[unresolved-import]
    )

    df = pop.get(properties=["model_template", "morphology"])
    hoc_dir = Path(pop.config.get("biophysical_neuron_models_dir", ""))

    updated_holding: dict[int, float] = {}
    updated_threshold: dict[int, float] = {}

    for node_id, row in df.iterrows():
        template_ref = row["model_template"]
        if not template_ref or ":" not in template_ref:
            continue

        parts = template_ref.split(":", 1)
        template_file = parts[1] + "." + parts[0]
        template_path = hoc_dir / template_file

        if not template_path.exists():
            continue

        morph_path = _resolve_node_morphology(pop, node_id)
        if not morph_path:
            continue

        try:
            props = compute_memodel_properties_v2(
                template_path=str(template_path),
                morphology_path=str(morph_path),
                template_format="v6",
                holding_voltage=-85.0,
                emodel_properties=None,
            )
            updated_holding[node_id] = props["holding_current"]
            updated_threshold[node_id] = props["threshold_current"]
            L.debug(
                "Node %s: holding=%.4f, threshold=%.4f",
                node_id,
                props["holding_current"],
                props["threshold_current"],
            )
        except Exception as e:  # noqa: BLE001
            L.warning("Failed to compute dynamic params for node %s: %s", node_id, e)
            continue

    return updated_holding, updated_threshold


def _resolve_node_morphology(pop: NodePopulation, node_id: int) -> Path | None:
    """Resolve the morphology path for a node, trying swc then asc extensions."""
    try:
        morph_path = pop.morph.get_morphology_path(node_id, extension="swc")
        if not Path(morph_path).exists():
            morph_path = pop.morph.get_morphology_path(node_id, extension="asc")
    except Exception:  # noqa: BLE001
        return None
    if not Path(morph_path).exists():
        return None
    return Path(morph_path)


def _write_dynamics_to_h5(
    circuit_config_path: Path,
    population_name: str,
    holding: dict[int, float],
    threshold: dict[int, float],
) -> None:
    """Write updated dynamic params back to the nodes H5 file."""
    import numpy as np  # noqa: PLC0415

    config = libsonata.CircuitConfig.from_file(str(circuit_config_path))
    cfg = json.loads(config.expanded_json)

    nodes_file = None
    for entry in cfg.get("networks", {}).get("nodes", []):
        if population_name in entry.get("populations", {}):
            nodes_file = entry.get("nodes_file")
            break

    if not nodes_file:
        L.warning("Could not find nodes file for population '%s'", population_name)
        return

    nodes_path = Path(nodes_file)
    if not nodes_path.is_absolute():
        nodes_path = circuit_config_path.parent / nodes_path

    L.info("Writing dynamic params to %s (population: %s)", nodes_path, population_name)

    with h5py.File(nodes_path, "r+") as f:
        pop_group = f["nodes"][population_name]
        group = pop_group["0"]

        if "dynamics_params" not in group:
            group.create_group("dynamics_params")
        dyn = group["dynamics_params"]

        n_nodes = (
            len(group["morphology"])
            if "morphology" in group
            else pop_group["node_type_id"].shape[0]
        )

        _update_h5_dataset(dyn, "holding_current", holding, n_nodes, np)
        _update_h5_dataset(dyn, "threshold_current", threshold, n_nodes, np)

    L.info("Dynamic params written for %d nodes", len(holding))


def _update_h5_dataset(
    group: h5py.Group,
    name: str,
    values: dict[int, float],
    n_nodes: int,
    np: types.ModuleType,
) -> None:
    """Update or create a dataset in an HDF5 group with per-node values."""
    arr = group[name][:] if name in group else np.zeros(n_nodes, dtype=np.float32)
    for node_id, val in values.items():
        arr[node_id] = val
    if name in group:
        group[name][:] = arr
    else:
        group.create_dataset(name, data=arr)


# ---------------------------------------------------------------------------
# Subset checks: customized circuit must not introduce new morphologies or
# emodels that don't exist in the parent (adopted from PR #829).
# ---------------------------------------------------------------------------


def _check_content_subset_of_parent(
    db_client: Client, parent_circuit_id: UUID, child_config_path: Path
) -> list[str]:
    """Verify morphology names and model_templates in the child are a subset of the parent."""
    from bluepysnap import Circuit as SnapCircuit  # noqa: PLC0415

    errors: list[str] = []

    # Stage parent to a temp dir to inspect its contents
    try:
        parent = db_client.get_entity(entity_id=parent_circuit_id, entity_type=models.Circuit)
    except Exception as e:  # noqa: BLE001
        L.warning("Could not fetch parent circuit %s for subset check: %s", parent_circuit_id, e)
        return errors

    with tempfile.TemporaryDirectory() as parent_tmp:
        parent_dir = Path(parent_tmp) / "parent"
        parent_dir.mkdir()
        try:
            parent_config_path = stage_circuit(db_client, model=parent, output_dir=parent_dir)
        except Exception as e:  # noqa: BLE001
            L.warning("Could not stage parent circuit for subset check: %s", e)
            return errors

        try:
            parent_circuit = SnapCircuit(str(parent_config_path))
            child_circuit = SnapCircuit(str(child_config_path))
        except Exception as e:  # noqa: BLE001
            L.warning("Could not load circuits for subset check: %s", e)
            return errors

        errors.extend(_check_morphology_subset(child_circuit, parent_circuit))
        errors.extend(_check_emodel_subset(child_circuit, parent_circuit))

    return errors


def _check_morphology_subset(child: SnapCircuitType, parent: SnapCircuitType) -> list[str]:
    """Check that morphology names in child are a subset of parent's."""
    errors: list[str] = []
    parent_names = _get_morph_names(parent)
    child_names = _get_morph_names(child)
    extra = child_names - parent_names
    if extra:
        errors.append(f"{len(extra)} morphology name(s) in customized circuit not found in parent")
    return errors


def _check_emodel_subset(child: SnapCircuitType, parent: SnapCircuitType) -> list[str]:
    """Check that model_template values in child are a subset of parent's."""
    errors: list[str] = []
    parent_templates = _get_model_templates(parent)
    child_templates = _get_model_templates(child)
    extra = child_templates - parent_templates
    if extra:
        errors.append(f"{len(extra)} model_template(s) in customized circuit not found in parent")
    return errors


def _get_morph_names(circuit: SnapCircuitType) -> set[str]:
    """Get all unique morphology names referenced by a circuit's node populations."""
    names: set[str] = set()
    for npop in circuit.nodes.population_names:
        nodes = circuit.nodes[npop]
        if "morphology" in nodes.property_names:
            names.update(nodes.get(properties="morphology").to_list())
    return names


def _get_model_templates(circuit: SnapCircuitType) -> set[str]:
    """Get all unique model_template values referenced by a circuit's node populations."""
    templates: set[str] = set()
    for npop in circuit.nodes.population_names:
        nodes = circuit.nodes[npop]
        if "model_template" in nodes.property_names:
            templates.update(nodes.get(properties="model_template").to_list())
    return templates


def _check_node_columns_unchanged(
    db_client: Client, parent_circuit_id: UUID, child_config_path: Path
) -> list[str]:
    """Check that only model_template/etype columns differ from parent nodes.

    Adopted from Aurélien's PR #837. Returns warnings (not errors) since dynamic
    params are recomputed anyway.
    """
    warnings: list[str] = []
    allowed_changes = {"model_template", "etype"}

    try:
        parent = db_client.get_entity(entity_id=parent_circuit_id, entity_type=models.Circuit)
    except Exception:  # noqa: BLE001
        return warnings

    with tempfile.TemporaryDirectory() as parent_tmp:
        parent_dir = Path(parent_tmp) / "parent"
        parent_dir.mkdir()
        try:
            parent_config_path = stage_circuit(db_client, model=parent, output_dir=parent_dir)
        except Exception:  # noqa: BLE001
            return warnings

        child_config = libsonata.CircuitConfig.from_file(str(child_config_path))
        parent_config = libsonata.CircuitConfig.from_file(str(parent_config_path))

        for pop_name in child_config.node_populations:
            if pop_name not in parent_config.node_populations:
                continue

            try:
                child_pop = child_config.node_population(pop_name)
                parent_pop = parent_config.node_population(pop_name)
            except Exception:  # noqa: BLE001, S112
                continue

            child_attrs = set(child_pop.attribute_names)
            parent_attrs = set(parent_pop.attribute_names)

            if child_attrs != parent_attrs:
                warnings.append(
                    f"Population '{pop_name}': attribute names differ from parent "
                    f"(added: {child_attrs - parent_attrs}, removed: {parent_attrs - child_attrs})"
                )
                continue

            # Check each attribute for unexpected changes
            selection = child_pop.select_all()
            for attr in child_attrs - allowed_changes:
                try:
                    child_vals = child_pop.get_attribute(attr, selection)
                    parent_vals = parent_pop.get_attribute(attr, selection)
                    if not (child_vals == parent_vals).all():
                        warnings.append(
                            f"Population '{pop_name}': attribute '{attr}' was modified "
                            f"(only {allowed_changes} changes are expected)"
                        )
                except Exception:  # noqa: BLE001, S112
                    continue

    return warnings
