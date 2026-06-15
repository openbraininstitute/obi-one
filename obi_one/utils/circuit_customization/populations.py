"""Circuit customization: population modification."""

import shutil
from pathlib import Path

from bluepysnap import Circuit
from entitysdk import models
from entitysdk.client import Client

from obi_one.utils.circuit_customization.download import fetch_directory, get_sonata_asset
from obi_one.utils.circuit_customization.validations.populations import check_input_files


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

    # Replace circuit config with custom one
    if new_circuit_config_path:
        shutil.copy(new_circuit_config_path, config_path)

    # Load new circuit
    new_circuit = Circuit(config_path)

    # Replace node sets file with custom one, or remove existing one
    node_sets_file = new_circuit.config.get("node_sets_file", "")
    if node_sets_file:
        node_sets_file = Path(node_sets_file)
        # Node sets file specified in new circuit config
        if new_node_sets_path:
            shutil.copy(new_node_sets_path, node_sets_file)

        if not node_sets_file.is_file():
            msg = f"Node sets file '{node_sets_file}' missing!"
            raise ValueError(msg)
    else:
        # Node sets file not specified in new circuit config
        if new_node_sets_path:
            msg = (
                f"New node sets file '{new_node_sets_path}' provided"
                " but not specified in circuit config!"
            )
            raise ValueError(msg)

        old_node_sets_file = parent_circuit.config.get("node_sets_file", "")
        if old_node_sets_file:
            Path(old_node_sets_file).unlink(missing_ok=True)

    # TODO: Check if node populations were removed

    return new_circuit_path, from_circuit
