"""Staging logic for customized circuits.

Stages a parent circuit (via entitysdk) and overlays user-provided overrides
to produce a complete circuit directory ready for validation or simulation.
"""

import json
import logging
import shutil
from pathlib import Path

import h5py
import libsonata
from entitysdk.client import Client
from entitysdk.models import Circuit
from entitysdk.staging.circuit import stage_circuit

L = logging.getLogger(__name__)


def stage_customized_circuit(
    client: Client,
    *,
    parent: Circuit,
    output_dir: Path,
    edge_overrides: list[Path] | None = None,
    emodel_overrides: list[Path] | None = None,
    emodel_population_map: dict[str, str] | None = None,
    mechanism_overrides: list[Path] | None = None,
    node_overrides: list[Path] | None = None,
    node_sets_override: Path | None = None,
    circuit_config_override: Path | None = None,
) -> Path:
    """Stage a customized circuit by overlaying overrides on the parent.

    Args:
        client: EntitySDK client.
        parent: The parent Circuit entity (must have assets).
        output_dir: Directory where the staged circuit will be written.
        edge_overrides: Edge H5 files to replace in the parent.
        emodel_overrides: HOC files to add/replace.
        emodel_population_map: Maps HOC filename → population name for per-population
            placement. Files not in the map go to the component-level model dir.
        mechanism_overrides: MOD files to add/replace.
        node_overrides: Node H5 files to replace in the parent.
        node_sets_override: Replacement SONATA nodeset JSON file.
        circuit_config_override: Replacement circuit_config.json.

    Returns:
        Path to the staged circuit_config.json.
    """
    # 1. Stage parent circuit (symlinks to mounted EFS)
    circuit_config_path = stage_circuit(client, model=parent, output_dir=output_dir)
    circuit_dir = circuit_config_path.parent

    L.info("Parent circuit staged at %s", circuit_dir)

    # 2. Load parent circuit_config (expanded paths) for overlay decisions
    ls_config = libsonata.CircuitConfig.from_file(str(circuit_config_path))
    parent_config = json.loads(ls_config.expanded_json)

    # 3. Apply overrides
    if edge_overrides:
        _apply_file_overrides(edge_overrides, circuit_dir, parent_config, component_type="edges")

    if node_overrides:
        _apply_file_overrides(node_overrides, circuit_dir, parent_config, component_type="nodes")

    if emodel_overrides:
        _apply_emodel_overrides(
            emodel_overrides, emodel_population_map or {}, parent_config, circuit_dir
        )

    if mechanism_overrides:
        mod_dir = _resolve_mod_dir(parent_config, circuit_dir)
        _copy_into(mechanism_overrides, mod_dir)

    if node_sets_override:
        _apply_node_sets_override(node_sets_override, circuit_dir, circuit_config_path)

    if circuit_config_override:
        _replace_file(circuit_config_override, circuit_config_path)
        L.info("Replaced circuit_config.json with override")

    # 4. Remove network files from the parent that the override config no longer references
    if circuit_config_override:
        _remove_stale_network_files(circuit_dir, circuit_config_path, parent_config)

    return circuit_config_path


def _apply_file_overrides(
    overrides: list[Path], circuit_dir: Path, config: dict, component_type: str
) -> None:
    """Replace edge/node files by matching the population names stored inside each H5 upload.

    SONATA H5 files declare their population names under /nodes/<pop> or /edges/<pop>.
    We read those names from the uploaded file and use them to locate the corresponding
    file in the parent circuit, rather than relying on filename matching.

    Raises:
        ValueError: if an uploaded file contains a population not found in the parent circuit.
    """
    file_key = "nodes_file" if component_type == "nodes" else "edges_file"

    # Build map: population_name -> path of the H5 file in the parent circuit
    pop_to_parent_file: dict[str, Path] = {}
    for entry in config.get("networks", {}).get(component_type, []):
        h5_file = entry.get(file_key)
        if not h5_file:
            continue
        h5_path = Path(h5_file) if Path(h5_file).is_absolute() else circuit_dir / h5_file
        try:
            with h5py.File(h5_path, "r") as f:
                for pop_name in f.get(component_type, {}):
                    pop_to_parent_file[pop_name] = h5_path
        except Exception as e:  # noqa: BLE001
            L.warning("Could not read parent %s file '%s': %s", component_type, h5_path.name, e)

    for override in overrides:
        try:
            with h5py.File(override, "r") as f:
                upload_populations = list(f.get(component_type, {}).keys())
        except Exception as e:
            msg = f"Could not read populations from uploaded file '{override.name}': {e}"
            raise ValueError(msg) from e

        for pop_name in upload_populations:
            if pop_name not in pop_to_parent_file:
                known = sorted(pop_to_parent_file.keys())
                msg = (
                    f"Uploaded {component_type} file '{override.name}' contains population"
                    f" '{pop_name}' which is not present in the parent circuit"
                    f" (known populations: {known})"
                )
                raise ValueError(msg)
            target = pop_to_parent_file[pop_name]
            _replace_file(override, target)
            L.info(
                "Replaced %s file for population '%s' (%s -> %s)",
                component_type,
                pop_name,
                override.name,
                target.name,
            )


def _apply_emodel_overrides(
    overrides: list[Path],
    population_map: dict[str, str],
    config: dict,
    circuit_dir: Path,
) -> None:
    """Place HOC files in the appropriate population-specific or component-level model dir.

    population_map maps filename → population name. Files not in the map fall back to
    the component-level biophysical_neuron_models_dir.
    """
    # Build map: population_name -> resolved model dir (from per-population config overrides)
    pop_dirs: dict[str, Path] = {}
    for entry in config.get("networks", {}).get("nodes", []):
        for pop_name, pop_cfg in entry.get("populations", {}).items():
            pop_model_dir = pop_cfg.get("biophysical_neuron_models_dir", "")
            if pop_model_dir:
                p = Path(pop_model_dir)
                pop_dirs[pop_name] = p if p.is_absolute() else circuit_dir / p

    component_dir = _resolve_hoc_dir(config, circuit_dir)

    for override in overrides:
        target_pop = population_map.get(override.name)
        if target_pop and target_pop in pop_dirs:
            target_dir = pop_dirs[target_pop]
            target_dir.mkdir(parents=True, exist_ok=True)
            _copy_into([override], target_dir)
            L.info("Placed HOC '%s' into population '%s' model dir", override.name, target_pop)
        else:
            _copy_into([override], component_dir)


def _apply_node_sets_override(
    node_sets_path: Path, circuit_dir: Path, circuit_config_path: Path
) -> None:
    """Copy the nodeset file into the circuit dir and patch circuit_config if needed."""
    dest = circuit_dir / node_sets_path.name
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    shutil.copy2(node_sets_path, dest)
    L.info("Copied nodeset file: %s", node_sets_path.name)

    # If the current circuit_config doesn't reference node_sets_file, add the reference
    try:
        cfg = json.loads(circuit_config_path.read_text(encoding="utf-8"))
        if not cfg.get("node_sets_file"):
            cfg["node_sets_file"] = node_sets_path.name
            circuit_config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            L.info("Patched circuit_config.json to reference nodeset: %s", node_sets_path.name)
    except Exception:  # noqa: BLE001
        L.warning("Could not patch circuit_config.json for nodeset file", exc_info=True)


def _remove_stale_network_files(
    circuit_dir: Path, circuit_config_path: Path, parent_config: dict
) -> None:
    """Unlink parent network files no longer referenced by the override circuit_config.

    Only removes symlinks (files that came from the parent via EFS staging), never
    files the user explicitly uploaded.
    """
    try:
        override_cfg = json.loads(circuit_config_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        L.warning("Could not parse final circuit_config for stale file cleanup", exc_info=True)
        return

    parent_names = _network_file_names(parent_config)
    override_names = _network_file_names(override_cfg)
    stale_names = parent_names - override_names

    for stale_name in stale_names:
        for candidate in circuit_dir.rglob(stale_name):
            if candidate.is_symlink():
                candidate.unlink()
                L.info("Removed stale network symlink: %s", candidate)


def _network_file_names(cfg: dict) -> set[str]:
    """Collect the bare filenames of all nodes, edges, and nodeset files in a config dict."""
    names: set[str] = set()
    for entry in cfg.get("networks", {}).get("nodes", []):
        if f := entry.get("nodes_file"):
            names.add(Path(f).name)
    for entry in cfg.get("networks", {}).get("edges", []):
        if f := entry.get("edges_file"):
            names.add(Path(f).name)
    if f := cfg.get("node_sets_file"):
        names.add(Path(f).name)
    return names


def _resolve_hoc_dir(config: dict, circuit_dir: Path) -> Path:
    """Find or create the HOC/e-model directory from the component-level config."""
    components = config.get("components", {})
    hoc_dir = components.get("biophysical_neuron_models_dir", "")
    if hoc_dir:
        path = Path(hoc_dir) if Path(hoc_dir).is_absolute() else circuit_dir / hoc_dir
    else:
        path = circuit_dir / "hoc"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_mod_dir(config: dict, circuit_dir: Path) -> Path:
    """Find or create the MOD/mechanisms directory from circuit config."""
    components = config.get("components", {})
    mod_dir = components.get("mechanisms_dir", "")
    if mod_dir:
        path = Path(mod_dir) if Path(mod_dir).is_absolute() else circuit_dir / mod_dir
    else:
        path = circuit_dir / "mod"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _copy_into(files: list[Path], target_dir: Path) -> None:
    """Copy files into target directory, replacing any existing with same name."""
    for f in files:
        dest = target_dir / f.name
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        shutil.copy2(f, dest)
        L.info("Copied %s -> %s", f.name, target_dir)


def _replace_file(source: Path, target: Path) -> None:
    """Replace a target file (which may be a symlink) with source."""
    if target.exists() or target.is_symlink():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
