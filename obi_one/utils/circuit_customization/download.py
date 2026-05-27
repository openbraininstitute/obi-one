"""Download circuit components from entitycore."""

import logging
import tempfile
from pathlib import Path
from uuid import UUID

import bluepysnap as snap
from entitysdk.client import Client
from entitysdk.models.asset import Asset
from entitysdk.models.circuit import Circuit
from entitysdk.types import FetchFileStrategy

L = logging.getLogger(__name__)


def _get_sonata_asset(db_client: Client, circuit_id: str) -> tuple[Circuit, Asset]:
    """Get the sonata_circuit directory asset from a circuit entity.

    Args:
        db_client: The entitycore SDK client.
        circuit_id: The ID of the circuit entity.

    Returns:
        Tuple of (circuit entity, sonata_circuit asset).

    Raises:
        ValueError: If the circuit does not have exactly one sonata_circuit asset.
    """
    circuit = db_client.get_entity(
        entity_id=circuit_id,  # ty:ignore[invalid-argument-type]
        entity_type=Circuit,
    )
    sonata_assets = [
        a for a in circuit.assets if a.is_directory and a.label.value == "sonata_circuit"
    ]
    if len(sonata_assets) != 1:
        msg = f"Circuit '{circuit_id}' must have exactly one 'sonata_circuit' directory asset."
        raise ValueError(msg)
    return circuit, sonata_assets[0]


def _fetch_file(
    db_client: Client,
    circuit_id: str,
    asset_id: UUID,
    rel_path: str,
    dest_dir: Path,
    *,
    output_filename: str | None = None,
) -> Path:
    """Fetch a single file from the sonata_circuit asset.

    Args:
        db_client: The entitycore SDK client.
        circuit_id: The ID of the circuit entity.
        asset_id: The ID of the sonata_circuit asset.
        rel_path: Relative path within the asset.
        dest_dir: Destination directory.
        output_filename: If provided, use this filename instead of the full rel_path
            for the output file location.

    Returns:
        Path to the downloaded file.
    """
    local_path = output_filename or rel_path
    output_path = dest_dir / local_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    db_client.fetch_file(
        entity_id=circuit_id,  # ty:ignore[invalid-argument-type]
        entity_type=Circuit,
        asset_id=asset_id,
        output_path=output_path,
        asset_path=rel_path,  # ty:ignore[invalid-argument-type]
        strategy=FetchFileStrategy.link_or_download,
    )
    L.info(f"Downloaded '{rel_path}' to '{output_path}'")
    return output_path


def download_electrical_models(
    circuit_id: str,
    db_client: Client,
    dest_dir: Path,
    node_population: str | None = None,
) -> list[Path]:
    """Download electrical models (hoc files) from a circuit.

    Electrical models are node-population specific. If node_population is given,
    downloads .hoc files for that population. If None, downloads for all populations
    into subfolders named by population.

    Args:
        circuit_id: The ID of the circuit entity.
        db_client: The entitycore SDK client.
        dest_dir: Destination directory to download files into.
        node_population: Name of the node population. If None, downloads for all.

    Returns:
        List of paths to the downloaded files.

    Raises:
        ValueError: If the specified node population does not exist.
        FileNotFoundError: If no .hoc files are found.
    """
    _, asset = _get_sonata_asset(db_client, circuit_id)

    with tempfile.TemporaryDirectory() as tmp:
        config_path = _fetch_file(db_client, circuit_id, asset.id, "circuit_config.json", Path(tmp))  # ty:ignore[invalid-argument-type]
        circuit = snap.Circuit(str(config_path))

        if node_population is not None:
            if node_population not in circuit.nodes.population_names:
                msg = (
                    f"Node population '{node_population}' not found in "
                    f"circuit '{circuit_id}'. "
                    f"Available populations: {circuit.nodes.population_names}"
                )
                raise ValueError(msg)
            populations = [node_population]
        else:
            populations = circuit.nodes.population_names

        # Collect (population_name, relative_path_of_hoc_dir) pairs
        pop_hoc_dirs = []
        for pop in populations:
            if circuit.nodes[pop].type == "virtual":
                continue
            hoc_dir = circuit.nodes[pop].config["biophysical_neuron_models_dir"]
            hoc_rel_path = str(Path(hoc_dir).relative_to(Path(tmp).resolve()))
            if not hoc_rel_path or hoc_rel_path == ".":
                L.info(f"No biophysical_neuron_models_dir for population '{pop}' - skipping.")
                continue
            pop_hoc_dirs.append((pop, hoc_rel_path))

    # List files in the asset
    file_list = db_client.list_directory(
        entity_id=circuit_id,  # ty:ignore[invalid-argument-type]
        entity_type=Circuit,
        asset_id=asset.id,  # ty:ignore[invalid-argument-type]
    )

    downloaded = []
    for pop, hoc_rel_path in pop_hoc_dirs:
        hoc_files = [
            str(path)
            for path in file_list.files
            if str(path).startswith(hoc_rel_path + "/") and str(path).endswith(".hoc")
        ]

        if not hoc_files:
            if node_population is not None:
                msg = (
                    f"No .hoc files found in '{hoc_rel_path}' for "
                    f"population '{pop}' of circuit '{circuit_id}'."
                )
                raise FileNotFoundError(msg)
            L.info(f"No .hoc files found for population '{pop}' - skipping.")
            continue

        pop_dest_dir = dest_dir / pop if node_population is None else dest_dir

        downloaded.extend(
            _fetch_file(
                db_client,
                circuit_id,
                asset.id,  # ty:ignore[invalid-argument-type]
                rel_path,
                pop_dest_dir,
                output_filename=Path(rel_path).name,
            )
            for rel_path in hoc_files
        )

    if not downloaded:
        pop_desc = "specified" if node_population else "any"
        msg = f"No .hoc files found in {pop_desc} node population of circuit '{circuit_id}'."
        raise FileNotFoundError(msg)

    L.info(f"Downloaded {len(downloaded)} electrical model file(s) for circuit '{circuit_id}'")
    return downloaded


def download_mechanisms(circuit_id: str, db_client: Client, dest_dir: Path) -> list[Path]:
    """Download mechanisms (mod files) from a circuit.

    The directory is given by components/mechanisms_dir in the circuit config.
    Falls back to /mod if not specified or empty. Downloads all .mod files
    within that directory.

    Args:
        circuit_id: The ID of the circuit entity.
        db_client: The entitycore SDK client.
        dest_dir: Destination directory to download files into.

    Returns:
        List of paths to the downloaded files.

    Raises:
        FileNotFoundError: If no .mod files are found.
    """
    _, asset = _get_sonata_asset(db_client, circuit_id)

    with tempfile.TemporaryDirectory() as tmp:
        config_path = _fetch_file(db_client, circuit_id, asset.id, "circuit_config.json", Path(tmp))  # ty:ignore[invalid-argument-type]
        circuit = snap.Circuit(str(config_path))

        mechanisms_dir = circuit.config.get("components", {}).get("mechanisms_dir")
        if mechanisms_dir:
            mechanisms_rel_path = str(Path(mechanisms_dir).relative_to(Path(tmp).resolve()))
        if not mechanisms_dir or mechanisms_rel_path == ".":
            mechanisms_rel_path = "mod"

    # List files in the asset and filter for .mod files in the mechanisms directory
    file_list = db_client.list_directory(
        entity_id=circuit_id,  # ty:ignore[invalid-argument-type]
        entity_type=Circuit,
        asset_id=asset.id,  # ty:ignore[invalid-argument-type]
    )
    mod_files = [
        str(path)
        for path in file_list.files
        if str(path).startswith(mechanisms_rel_path + "/") and str(path).endswith(".mod")
    ]

    if not mod_files:
        msg = f"No .mod files found in '{mechanisms_rel_path}' for circuit '{circuit_id}'."
        raise FileNotFoundError(msg)

    downloaded = [
        _fetch_file(
            db_client,
            circuit_id,
            asset.id,  # ty:ignore[invalid-argument-type]
            rel_path,
            dest_dir,
            output_filename=Path(rel_path).name,
        )
        for rel_path in mod_files
    ]

    L.info(f"Downloaded {len(downloaded)} mechanism file(s) for circuit '{circuit_id}'")
    return downloaded


def download_circuit_config(circuit_id: str, db_client: Client, dest_dir: Path) -> Path:
    """Download the circuit config file from a circuit.

    Args:
        circuit_id: The ID of the circuit entity.
        db_client: The entitycore SDK client.
        dest_dir: Destination directory to download the file into.

    Returns:
        Path to the downloaded file.
    """
    _, asset = _get_sonata_asset(db_client, circuit_id)
    return _fetch_file(db_client, circuit_id, asset.id, "circuit_config.json", dest_dir)  # ty:ignore[invalid-argument-type]


def download_node_sets(circuit_id: str, db_client: Client, dest_dir: Path) -> Path:
    """Download the node sets file from a circuit.

    The file location is determined by the "node_sets_file" key in the circuit config.
    Uses bluepysnap to resolve any path placeholders in the config.

    Args:
        circuit_id: The ID of the circuit entity.
        db_client: The entitycore SDK client.
        dest_dir: Destination directory to download the file into.

    Returns:
        Path to the downloaded file.
    """
    _, asset = _get_sonata_asset(db_client, circuit_id)

    # Fetch circuit config to a temp location and resolve paths via bluepysnap
    with tempfile.TemporaryDirectory() as tmp:
        config_path = _fetch_file(db_client, circuit_id, asset.id, "circuit_config.json", Path(tmp))  # ty:ignore[invalid-argument-type]
        circuit = snap.Circuit(str(config_path))
        node_sets_abs_path = Path(circuit.config["node_sets_file"])
        node_sets_rel_path = str(node_sets_abs_path.relative_to(Path(tmp).resolve()))

    return _fetch_file(db_client, circuit_id, asset.id, node_sets_rel_path, dest_dir)  # ty:ignore[invalid-argument-type]


def download_id_mapping(circuit_id: str, db_client: Client, dest_dir: Path) -> Path:
    """Download the ID mapping file from a circuit.

    First checks if a path is specified under components/provenance/id_mapping
    in the circuit config. If not, falls back to id_mapping.json in the root folder.

    Args:
        circuit_id: The ID of the circuit entity.
        db_client: The entitycore SDK client.
        dest_dir: Destination directory to download the file into.

    Returns:
        Path to the downloaded file.
    """
    _, asset = _get_sonata_asset(db_client, circuit_id)

    with tempfile.TemporaryDirectory() as tmp:
        config_path = _fetch_file(db_client, circuit_id, asset.id, "circuit_config.json", Path(tmp))  # ty:ignore[invalid-argument-type]
        circuit = snap.Circuit(str(config_path))

        # Check components/provenance/id_mapping in config
        config = circuit.config
        id_mapping_path = config.get("components", {}).get("provenance", {}).get("id_mapping")

        if id_mapping_path:
            id_mapping_abs = Path(id_mapping_path)
            if id_mapping_abs.is_absolute():
                rel_path = str(id_mapping_abs.relative_to(Path(tmp).resolve()))
            else:
                rel_path = id_mapping_path
        else:
            # Fall back to id_mapping.json in root folder
            rel_path = "id_mapping.json"

    return _fetch_file(db_client, circuit_id, asset.id, rel_path, dest_dir)  # ty:ignore[invalid-argument-type]
