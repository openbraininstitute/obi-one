"""Circuit customization: population modification."""

from pathlib import Path

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

    # TODO: Replace files in new_circuit_path with customized ones

    return new_circuit_path, from_circuit
