"""Circuit customization: population modification."""

import shutil
from pathlib import Path

from bluepysnap import Circuit
from entitysdk import models
from entitysdk.client import Client

from obi_one.utils.circuit_customization.download import fetch_directory, get_sonata_asset
from obi_one.utils.circuit_customization.validations.populations import (
    check_customized_circuit,
    check_input_files,
)


def _update_circuit_config(
    config_path: Path,
    new_circuit_config_path: Path | None,
) -> Circuit:
    """Replace the circuit config file and return the loaded circuit.

    Args:
        config_path: Path to the existing circuit_config.json in the new circuit folder.
        new_circuit_config_path: Path to the replacement config file, or None to keep existing.

    Returns:
        The loaded Circuit (from the potentially updated config).
    """
    if new_circuit_config_path:
        shutil.copy(new_circuit_config_path, config_path)

    return Circuit(config_path)


def _update_node_sets(
    new_circuit: Circuit,
    parent_circuit: Circuit,
    new_node_sets_path: Path | None,
) -> None:
    """Replace or remove the node sets file.

    If the new circuit config references a node sets file:
      - Replaces it with the custom one if provided.
      - Validates the file exists.

    If the new circuit config does not reference a node sets file:
      - Raises if a custom node sets file was provided (nowhere to put it).
      - Removes the old node sets file from the parent if it existed.

    Args:
        new_circuit: The loaded new circuit (after config update).
        parent_circuit: The loaded parent circuit (before config update).
        new_node_sets_path: Path to a replacement node_sets.json file, or None.

    Raises:
        ValueError: If validation fails.
    """
    node_sets_file = new_circuit.config.get("node_sets_file", "")
    if node_sets_file:
        node_sets_file = Path(node_sets_file)
        if new_node_sets_path:
            shutil.copy(new_node_sets_path, node_sets_file)

        if not node_sets_file.is_file():
            msg = f"Node sets file '{node_sets_file}' missing!"
            raise ValueError(msg)
    else:
        if new_node_sets_path:
            msg = (
                f"New node sets file '{new_node_sets_path}' provided"
                " but not specified in circuit config!"
            )
            raise ValueError(msg)

        old_node_sets_file = parent_circuit.config.get("node_sets_file", "")
        if old_node_sets_file:
            Path(old_node_sets_file).unlink(missing_ok=True)


def _update_node_populations(
    new_circuit: Circuit,
    parent_circuit: Circuit,
    new_node_population_paths: dict[str, Path] | None,
) -> None:
    """Replace or remove node population files.

    Copies custom node population files over the existing ones, validates that
    all referenced files exist, and removes old files no longer referenced.

    Args:
        new_circuit: The loaded new circuit (after config update).
        parent_circuit: The loaded parent circuit (before config update).
        new_node_population_paths: Mapping of population name to replacement .h5 file,
            or None if no replacements.

    Raises:
        ValueError: If a provided population name is not in the config, or if
            a referenced file is missing after replacement.
    """
    npop_files = {
        npop: Path(new_circuit.nodes[npop].h5_filepath)
        for npop in new_circuit.nodes.population_names
    }

    if new_node_population_paths:
        for npop_name, new_path in new_node_population_paths.items():
            if npop_name not in npop_files:
                msg = f"Node population '{npop_name}' provided but not found in circuit config!"
                raise ValueError(msg)
            shutil.copy(new_path, npop_files[npop_name])

    for npop_name, npop_file in npop_files.items():
        if not npop_file.is_file():
            msg = f"Node population file '{npop_file}' for '{npop_name}' missing!"
            raise ValueError(msg)

    # Remove old node population files no longer referenced
    old_npop_files = {
        Path(parent_circuit.nodes[npop].h5_filepath)
        for npop in parent_circuit.nodes.population_names
    }
    for old_npop_file in old_npop_files:
        if old_npop_file not in npop_files.values():
            old_npop_file.unlink(missing_ok=True)


def _update_edge_populations(
    new_circuit: Circuit,
    parent_circuit: Circuit,
    new_edge_population_paths: dict[str, Path] | None,
) -> None:
    """Replace or remove edge population files.

    Copies custom edge population files over the existing ones, validates that
    all referenced files exist, and removes old files no longer referenced.

    Args:
        new_circuit: The loaded new circuit (after config update).
        parent_circuit: The loaded parent circuit (before config update).
        new_edge_population_paths: Mapping of population name to replacement .h5 file,
            or None if no replacements.

    Raises:
        ValueError: If a provided population name is not in the config, or if
            a referenced file is missing after replacement.
    """
    epop_files = {
        epop: Path(new_circuit.edges[epop].h5_filepath)
        for epop in new_circuit.edges.population_names
    }

    if new_edge_population_paths:
        for epop_name, new_path in new_edge_population_paths.items():
            if epop_name not in epop_files:
                msg = f"Edge population '{epop_name}' provided but not found in circuit config!"
                raise ValueError(msg)
            shutil.copy(new_path, epop_files[epop_name])

    for epop_name, epop_file in epop_files.items():
        if not epop_file.is_file():
            msg = f"Edge population file '{epop_file}' for '{epop_name}' missing!"
            raise ValueError(msg)

    # Remove old edge population files no longer referenced
    old_epop_files = {
        Path(parent_circuit.edges[epop].h5_filepath)
        for epop in parent_circuit.edges.population_names
    }
    for old_epop_file in old_epop_files:
        if old_epop_file not in epop_files.values():
            old_epop_file.unlink(missing_ok=True)


def create_modified_circuit(
    db_client: Client,
    circuit_id: str,
    *,
    new_circuit_config_path: str | Path | None = None,
    new_node_sets_path: str | Path | None = None,
    new_node_population_paths: dict[str, str | Path] | None = None,
    new_edge_population_paths: dict[str, str | Path] | None = None,
    new_circuit_path: str | Path | None = None,
) -> tuple[Path, models.Circuit]:
    """Create a new circuit with modified populations.

    Downloads the parent circuit directory and replaces specified files with
    user-provided customizations.

    Args:
        db_client: The entitycore SDK client.
        circuit_id: The ID of the parent circuit entity.
        new_circuit_config_path: Path to a replacement circuit_config.json file.
        new_node_sets_path: Path to a replacement node_sets.json file.
        new_node_population_paths: Mapping of population name to replacement nodes .h5 file.
        new_edge_population_paths: Mapping of population name to replacement edges .h5 file.
        new_circuit_path: Path to the new circuit folder to be created.
            If None, defaults to a temporary directory.

    Returns:
        Tuple of (path to the new circuit folder, parent circuit entity).
    """
    # Validate customization input files
    (
        new_circuit_config_path,
        new_node_sets_path,
        new_node_population_paths,
        new_edge_population_paths,
    ) = check_input_files(
        new_circuit_config_path=new_circuit_config_path,
        new_node_sets_path=new_node_sets_path,
        new_node_population_paths=new_node_population_paths,
        new_edge_population_paths=new_edge_population_paths,
    )

    # Fetch parent circuit directory (writable)
    if new_circuit_path is None:
        msg = "new_circuit_path is required!"
        raise ValueError(msg)

    new_circuit_path = Path(new_circuit_path)
    if new_circuit_path.exists():
        msg = (
            f"New circuit path '{new_circuit_path}' already exists."
            " Please provide a different path or delete the existing one."
        )
        raise ValueError(msg)

    from_circuit, asset = get_sonata_asset(db_client, circuit_id)
    fetch_directory(db_client, circuit_id, asset.id, new_circuit_path, writable=True)
    config_path = new_circuit_path / "circuit_config.json"
    parent_circuit = Circuit(config_path)

    # Apply customizations
    new_circuit = _update_circuit_config(config_path, new_circuit_config_path)
    _update_node_sets(new_circuit, parent_circuit, new_node_sets_path)
    _update_node_populations(new_circuit, parent_circuit, new_node_population_paths)
    _update_edge_populations(new_circuit, parent_circuit, new_edge_population_paths)

    # Validate customizations

    # (1) Try loading circuit and get population sizes
    # (2) Try loading node sets
    # (3) Check if ID mapping is still valid, otherwise remove + warning
    # (4) Check if existing morphologies are still used and none missing
    # (5) Check if existing hoc files are still used and none missing

    check_customized_circuit(new_circuit_path)

    return new_circuit_path, from_circuit
