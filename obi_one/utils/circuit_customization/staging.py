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
from bluepysnap import Circuit as SnapCircuit
from entitysdk.client import Client
from entitysdk.models import Circuit
from entitysdk.staging.circuit import stage_circuit

from obi_one.scientific.library.circuit_id_mapping import validate_id_mapping_files

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
        edge_overrides: Edge H5 files to replace or add.
        emodel_overrides: HOC files to add/replace.
        emodel_population_map: Maps HOC filename → population name for per-population
            placement. Files not in the map go to the component-level model dir.
        mechanism_overrides: MOD files to add/replace.
        node_overrides: Node H5 files to replace or add.
        node_sets_override: Replacement SONATA nodeset JSON file.
        circuit_config_override: Replacement circuit_config.json. When provided,
            node/edge uploads may introduce populations declared in the override
            that are not present in the parent.

    Returns:
        Path to the staged circuit_config.json.
    """
    # 1. Stage parent circuit (symlinks to mounted EFS)
    circuit_config_path = stage_circuit(client, model=parent, output_dir=output_dir)
    circuit_dir = circuit_config_path.parent

    L.info("Parent circuit staged at %s", circuit_dir)

    # 2. Load parent circuit_config (expanded paths) for overlay decisions
    parent_config = _load_circuit_config(circuit_config_path)

    # 3. Apply circuit_config override first so subsequent placement uses the new layout
    if circuit_config_override:
        _replace_file(circuit_config_override, circuit_config_path)
        L.info("Replaced circuit_config.json with override")
        active_config = _load_circuit_config(circuit_config_path)
        allow_new_populations = True
    else:
        active_config = parent_config
        allow_new_populations = False

    # 4. Apply file overrides against the active (parent or overridden) config
    if edge_overrides:
        _apply_file_overrides(
            edge_overrides,
            circuit_dir,
            active_config,
            component_type="edges",
            allow_new_populations=allow_new_populations,
        )

    if node_overrides:
        _apply_file_overrides(
            node_overrides,
            circuit_dir,
            active_config,
            component_type="nodes",
            allow_new_populations=allow_new_populations,
        )

    if emodel_overrides:
        _apply_emodel_overrides(
            emodel_overrides, emodel_population_map or {}, active_config, circuit_dir
        )

    if mechanism_overrides:
        mod_dir = _resolve_mod_dir(active_config, circuit_dir)
        _copy_into(mechanism_overrides, mod_dir)

    if node_sets_override:
        _apply_node_sets_override(
            node_sets_override,
            circuit_dir,
            active_config,
            circuit_config_path,
            config_overridden=bool(circuit_config_override),
        )

    # 5. Remove network files from the parent that the override config no longer references
    if circuit_config_override:
        _remove_stale_network_files(circuit_dir, circuit_config_path, parent_config)

    # 6. Drop stale id_mapping.json before the staged circuit is registered
    _validate_staged_id_mapping(circuit_config_path)

    return circuit_config_path


def _load_circuit_config(circuit_config_path: Path) -> libsonata.CircuitConfig:
    """Load a circuit config with libsonata so paths and populations are expanded."""
    return libsonata.CircuitConfig.from_file(str(circuit_config_path))


def _validate_staged_id_mapping(circuit_config_path: Path) -> None:
    """Remove a stale brainbuilder id_mapping.json from the staged circuit copy."""
    circuit = SnapCircuit(str(circuit_config_path))
    for warning in validate_id_mapping_files(circuit_config_path, circuit):
        L.warning(warning)


def _population_names(config: libsonata.CircuitConfig, component_type: str) -> list[str]:
    return list(config.edge_populations if component_type == "edges" else config.node_populations)


def _population_elements_path(
    config: libsonata.CircuitConfig, component_type: str, pop_name: str
) -> str:
    if component_type == "nodes":
        return config.node_population_properties(pop_name).elements_path
    return config.edge_population_properties(pop_name).elements_path


def _network_file_for_population(
    config: libsonata.CircuitConfig, component_type: str, pop_name: str, circuit_dir: Path
) -> Path | None:
    """Resolve the nodes/edges H5 path for a population from circuit config."""
    if pop_name not in _population_names(config, component_type):
        return None
    elements_path = _population_elements_path(config, component_type, pop_name)
    if not elements_path:
        return None
    path = Path(elements_path)
    return path if path.is_absolute() else circuit_dir / path


def _apply_file_overrides(  # ruff: ignore[complex-structure, too-many-branches]
    overrides: list[Path],
    circuit_dir: Path,
    config: libsonata.CircuitConfig,
    component_type: str,
    *,
    allow_new_populations: bool = False,
) -> None:
    """Replace or add edge/node files by matching population names inside each H5 upload.

    SONATA H5 files declare their population names under /nodes/<pop> or /edges/<pop>.
    Existing populations replace the parent's file. When ``allow_new_populations`` is True
    (circuit_config override present), uploads for populations declared in ``config`` but
    absent from the parent are copied to the path referenced by that config.

    Raises:
        ValueError: if an uploaded population cannot be placed.
    """
    file_key = "nodes_file" if component_type == "nodes" else "edges_file"

    # Build map: population_name -> path of the H5 file in the parent circuit
    pop_to_parent_file: dict[str, Path] = {}
    for pop_name in _population_names(config, component_type):
        elements_path = _population_elements_path(config, component_type, pop_name)
        if not elements_path:
            continue
        h5_path = Path(elements_path)
        if not h5_path.is_absolute():
            h5_path = circuit_dir / h5_path
        if not h5_path.exists():
            # Config may already declare new populations whose files are not staged yet
            continue
        try:
            with h5py.File(h5_path, "r") as f:
                for staged_pop_name in f.get(component_type, {}):
                    pop_to_parent_file[staged_pop_name] = h5_path
        except Exception as e:  # ruff: ignore[blind-except]
            L.warning("Could not read parent %s file '%s': %s", component_type, h5_path.name, e)

    for override in overrides:
        try:
            with h5py.File(override, "r") as f:
                upload_populations = list(f.get(component_type, {}).keys())
        except Exception as e:
            msg = f"Could not read populations from uploaded file '{override.name}': {e}"
            raise ValueError(msg) from e

        for pop_name in upload_populations:
            if pop_name in pop_to_parent_file:
                target = pop_to_parent_file[pop_name]
                _replace_file(override, target)
                L.info(
                    "Replaced %s file for population '%s' (%s -> %s)",
                    component_type,
                    pop_name,
                    override.name,
                    target.name,
                )
                continue

            if allow_new_populations:
                target = _network_file_for_population(config, component_type, pop_name, circuit_dir)
                if target is not None:
                    _replace_file(override, target)
                    L.info(
                        "Added new %s file for population '%s' (%s -> %s)",
                        component_type,
                        pop_name,
                        override.name,
                        target.name,
                    )
                    continue

            known = sorted(pop_to_parent_file.keys())
            msg = (
                f"Uploaded {component_type} file '{override.name}' contains population"
                f" '{pop_name}' which is not present in the parent circuit"
                f" (known populations: {known})"
            )
            if allow_new_populations:
                msg += (
                    " and is not declared in the overridden circuit_config "
                    f"(expected a '{file_key}' entry for this population)"
                )
            raise ValueError(msg)


def _apply_emodel_overrides(
    overrides: list[Path],
    population_map: dict[str, str],
    config: libsonata.CircuitConfig,
    circuit_dir: Path,
) -> None:
    """Place HOC files in the appropriate population-specific or component-level model dir.

    population_map maps filename → population name. Files not in the map fall back to
    the component-level biophysical_neuron_models_dir.
    """
    pop_dirs: dict[str, Path] = {}
    for pop_name in config.node_populations:
        pop_model_dir = config.node_population_properties(pop_name).biophysical_neuron_models_dir
        if pop_model_dir:
            path = Path(pop_model_dir)
            pop_dirs[pop_name] = path if path.is_absolute() else circuit_dir / path

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
    node_sets_path: Path,
    circuit_dir: Path,
    config: libsonata.CircuitConfig,
    circuit_config_path: Path,
    *,
    config_overridden: bool,
) -> None:
    """Place the uploaded node sets file and make sure the circuit config points at it.

    An upload under the referenced filename simply replaces that file. Any other name
    is copied into the circuit directory and the config is repointed at it, so adding
    or renaming node sets needs no hand-written config override — the upload never
    silently ends up unreferenced.

    A user-supplied ``circuit_config.json`` is authoritative and never rewritten: the
    upload has to be the file that config references.

    Raises:
        ValueError: if a circuit config override was supplied that does not reference
            the uploaded file.
    """
    referenced = config.node_sets_path
    referenced_name = Path(referenced).name if referenced else None

    if referenced_name == node_sets_path.name:
        target = Path(referenced)
        if not target.is_absolute():
            target = circuit_dir / target
        _replace_file(node_sets_path, target)
        L.info("Replaced node sets file: %s", target)
        return

    if config_overridden:
        msg = (
            f"Uploaded node sets file '{node_sets_path.name}' is not referenced by the supplied"
            f" circuit_config.json (which references {referenced_name or 'no node sets file'})."
            " Upload the file the config declares, or point the config at this one."
        )
        raise ValueError(msg)

    target = circuit_dir / node_sets_path.name
    _replace_file(node_sets_path, target)
    _set_node_sets_reference(circuit_config_path, node_sets_path.name)
    L.info(
        "Added node sets file '%s' and pointed circuit_config.json at it (was: %s)",
        node_sets_path.name,
        referenced_name or "none",
    )


def _set_node_sets_reference(circuit_config_path: Path, node_sets_name: str) -> None:
    """Point the staged circuit config at a node sets file in the circuit directory.

    The staged config may be a symlink into the parent's storage, so it is rewritten
    as a fresh file: editing it in place would modify the parent circuit itself.
    """
    try:
        cfg = json.loads(circuit_config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        msg = f"Could not read circuit_config.json to reference '{node_sets_name}': {e}"
        raise ValueError(msg) from e

    cfg["node_sets_file"] = node_sets_name
    if circuit_config_path.is_symlink():
        circuit_config_path.unlink()
    circuit_config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _remove_stale_network_files(
    circuit_dir: Path,
    circuit_config_path: Path,
    parent_config: libsonata.CircuitConfig,
) -> None:
    """Unlink parent network files no longer referenced by the override circuit_config.

    Staging fetches the parent with a link-or-download strategy, so its files are
    symlinks into mounted storage on the cluster but plain copies elsewhere — both
    are removed here. Uploads are never at risk: they are only ever written to paths
    the override config references, and those names are by definition not stale.
    """
    try:
        override_config = _load_circuit_config(circuit_config_path)
    except libsonata.SonataError:
        L.warning("Could not parse final circuit_config for stale file cleanup", exc_info=True)
        return

    parent_names = _network_file_names(parent_config)
    override_names = _network_file_names(override_config)
    stale_names = parent_names - override_names

    for stale_name in stale_names:
        for candidate in circuit_dir.rglob(stale_name):
            if candidate.is_symlink() or candidate.is_file():
                candidate.unlink()
                L.info("Removed stale network file: %s", candidate)


def _network_file_names(config: libsonata.CircuitConfig) -> set[str]:
    """Collect the bare filenames of all nodes, edges, and nodeset files in a config."""
    names: set[str] = set()
    for pop_name in config.node_populations:
        elements_path = config.node_population_properties(pop_name).elements_path
        if elements_path:
            names.add(Path(elements_path).name)
    for pop_name in config.edge_populations:
        elements_path = config.edge_population_properties(pop_name).elements_path
        if elements_path:
            names.add(Path(elements_path).name)
    if config.node_sets_path:
        names.add(Path(config.node_sets_path).name)
    return names


def _component_dir(
    config: libsonata.CircuitConfig,
    circuit_dir: Path,
    *,
    component_key: str,
    fallback_name: str,
) -> Path:
    """Resolve a component-level directory declared in the circuit config."""
    components = json.loads(config.expanded_json).get("components", {})
    configured = components.get(component_key, "")
    if configured:
        path = Path(configured)
        resolved = path if path.is_absolute() else circuit_dir / path
    else:
        resolved = circuit_dir / fallback_name
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _resolve_hoc_dir(config: libsonata.CircuitConfig, circuit_dir: Path) -> Path:
    """Find or create the HOC/e-model directory from the component-level config."""
    return _component_dir(
        config,
        circuit_dir,
        component_key="biophysical_neuron_models_dir",
        fallback_name="hoc",
    )


def _resolve_mod_dir(config: libsonata.CircuitConfig, circuit_dir: Path) -> Path:
    """Find or create the MOD/mechanisms directory from circuit config."""
    if config.node_populations:
        first_population = next(iter(config.node_populations))
        mechanisms_dir = config.node_population_properties(first_population).mechanisms_dir
        if mechanisms_dir:
            path = Path(mechanisms_dir)
            resolved = path if path.is_absolute() else circuit_dir / path
            resolved.mkdir(parents=True, exist_ok=True)
            return resolved
    return _component_dir(
        config,
        circuit_dir,
        component_key="mechanisms_dir",
        fallback_name="mod",
    )


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
