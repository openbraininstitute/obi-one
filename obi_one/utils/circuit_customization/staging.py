"""Staging logic for customized circuits.

Stages a parent circuit (via entitysdk) and overlays user-provided overrides
to produce a complete circuit directory ready for validation or simulation.
"""

import json
import logging
import shutil
from pathlib import Path

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
    mechanism_overrides: list[Path] | None = None,
    node_overrides: list[Path] | None = None,
    circuit_config_override: Path | None = None,
) -> Path:
    """Stage a customized circuit by overlaying overrides on the parent.

    Args:
        client: EntitySDK client.
        parent: The parent Circuit entity (must have assets).
        output_dir: Directory where the staged circuit will be written.
        edge_overrides: Edge H5 files to replace in the parent.
        emodel_overrides: HOC files to add/replace.
        mechanism_overrides: MOD files to add/replace.
        node_overrides: Node H5 files to replace in the parent.
        circuit_config_override: Replacement circuit_config.json.

    Returns:
        Path to the staged circuit_config.json.
    """
    # 1. Stage parent circuit (symlinks to mounted EFS)
    circuit_config_path = stage_circuit(client, model=parent, output_dir=output_dir)
    circuit_dir = circuit_config_path.parent

    L.info("Parent circuit staged at %s", circuit_dir)

    # 2. Load circuit_config to find component paths using libsonata
    ls_config = libsonata.CircuitConfig.from_file(str(circuit_config_path))
    config = json.loads(ls_config.expanded_json)

    # 3. Apply overrides
    if edge_overrides:
        _apply_file_overrides(edge_overrides, circuit_dir, config, component_type="edges")

    if node_overrides:
        _apply_file_overrides(node_overrides, circuit_dir, config, component_type="nodes")

    if emodel_overrides:
        hoc_dir = _resolve_hoc_dir(config, circuit_dir)
        _copy_into(emodel_overrides, hoc_dir)

    if mechanism_overrides:
        mod_dir = _resolve_mod_dir(config, circuit_dir)
        _copy_into(mechanism_overrides, mod_dir)

    if circuit_config_override:
        # Replace the circuit_config entirely
        _replace_file(circuit_config_override, circuit_config_path)
        L.info("Replaced circuit_config.json with override")

    return circuit_config_path


def _apply_file_overrides(
    overrides: list[Path], circuit_dir: Path, config: dict, component_type: str
) -> None:
    """Replace edge/node files by matching filename against the config paths."""
    networks = config.get("networks", {})
    component_list = networks.get(component_type, [])

    # Build a map of filename -> full path from the config
    existing_files: dict[str, Path] = {}
    for entry in component_list:
        for _pop_name, _pop_info in entry.get("populations", {}).items():
            # populations may reference h5 file directly or via the entry
            pass
        h5_file = entry.get("nodes_file") or entry.get("edges_file")
        if h5_file:
            h5_path = Path(h5_file) if Path(h5_file).is_absolute() else circuit_dir / h5_file
            existing_files[h5_path.name] = h5_path

    for override in overrides:
        if override.name in existing_files:
            target = existing_files[override.name]
            _replace_file(override, target)
            L.info("Replaced %s: %s", component_type, override.name)
        else:
            # New file — place alongside existing ones
            if existing_files:
                dest_dir = next(iter(existing_files.values())).parent
            else:
                dest_dir = circuit_dir / component_type
                dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(override, dest_dir / override.name)
            L.info("Added new %s file: %s", component_type, override.name)


def _resolve_hoc_dir(config: dict, circuit_dir: Path) -> Path:
    """Find or create the HOC/e-model directory from circuit config."""
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
