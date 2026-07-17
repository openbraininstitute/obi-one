"""Asset validation and registration for circuits."""

import json
import logging
from pathlib import Path

from entitysdk import Client, models

L = logging.getLogger(__name__)


def _check_required_contents(file_path: Path, contents: list[str], *, is_directory: bool) -> None:
    """Validate that required files exist within a path."""
    if len(contents) == 0:
        return

    if is_directory:
        files_in_dir = {
            str(path.relative_to(file_path)): path
            for path in file_path.rglob("*")
            if path.is_file()
        }
        for file in contents:
            if file not in files_in_dir:
                msg = f"Required content '{file}' not found in '{file_path}'!"
                raise ValueError(msg)
    else:
        for file in contents:
            if file_path.name != file:
                msg = f"Required content '{file}' does not match '{file_path}'!"
                raise ValueError(msg)


def _check_matrix_folder(file_path: Path) -> None:
    """Validate connectivity matrix folder contents.

    Checks that matrix_config.json exists and all referenced matrix files are present.
    """
    matrix_files = {
        str(path.relative_to(file_path)): path for path in file_path.rglob("*") if path.is_file()
    }
    L.info(f"{len(matrix_files)} files in '{file_path}'")

    if "matrix_config.json" not in matrix_files:
        msg = "matrix_config.json missing!"
        raise ValueError(msg)

    with matrix_files["matrix_config.json"].open(encoding="utf-8") as f:
        mat_cfg = json.load(f)

    for pop in mat_cfg:
        for mat in mat_cfg[pop].values():
            mpath = mat["path"]
            if mpath not in matrix_files:
                msg = f"Matrix file '{mpath}' referenced in config but not found!"
                raise ValueError(msg)


CIRCUIT_ASSET_MAPPING: dict[str, dict] = {
    "sonata_circuit": {
        "is_directory": True,
        "content_type": "application/vnd.directory",
        "required_contents": ["circuit_config.json", "node_sets.json"],
        "required_validations": [],
    },
    "compressed_sonata_circuit": {
        "is_directory": False,
        "content_type": "application/gzip",
        "required_contents": ["circuit.gz"],
        "required_validations": [],
    },
    "circuit_connectivity_matrices": {
        "is_directory": True,
        "content_type": "application/vnd.directory",
        "required_contents": ["matrix_config.json"],
        "required_validations": [_check_matrix_folder],
    },
    "circuit_visualization": {
        "is_directory": False,
        "content_type": "image/webp",
        "required_contents": ["circuit_visualization.webp"],
        "required_validations": [],
    },
    "node_stats": {
        "is_directory": False,
        "content_type": "image/webp",
        "required_contents": ["node_stats.webp"],
        "required_validations": [],
    },
    "network_stats_a": {
        "is_directory": False,
        "content_type": "image/webp",
        "required_contents": ["network_stats_a.webp"],
        "required_validations": [],
    },
    "network_stats_b": {
        "is_directory": False,
        "content_type": "image/webp",
        "required_contents": ["network_stats_b.webp"],
        "required_validations": [],
    },
    "simulation_designer_image": {
        "is_directory": False,
        "content_type": "image/png",
        "required_contents": ["simulation_designer_image.png"],
        "required_validations": [],
    },
}


def register_asset(
    client: Client,
    file_path: Path | None,
    asset_label: str,
    registered_circuit: models.Circuit | None,
    *,
    dry_run: bool,
) -> models.Asset | None:
    """Register an asset for a circuit entity.

    Validates the asset label, file existence, and required contents before registration.

    Args:
        client: The entitycore SDK client.
        file_path: Path to the asset. None to skip.
        asset_label: Label identifying the asset type (must be in CIRCUIT_ASSET_MAPPING).
        registered_circuit: The circuit entity to attach the asset to.
        dry_run: If True, perform validation only without registering.

    Returns:
        The registered asset, or None if skipped or dry_run.
    """
    if file_path is None:
        L.info(f"No path for '{asset_label}' asset provided - skipping")
        return None

    if asset_label not in CIRCUIT_ASSET_MAPPING:
        msg = f"Asset label '{asset_label}' not supported!"
        raise ValueError(msg)

    if not file_path.exists():
        msg = f"File path '{file_path}' does not exist!"
        raise ValueError(msg)

    # Validate required contents
    asset_config = CIRCUIT_ASSET_MAPPING[asset_label]
    is_dir = asset_config["is_directory"]
    _check_required_contents(
        file_path,
        asset_config.get("required_contents", []),
        is_directory=is_dir,
    )

    # Run additional validations
    for val_fct in asset_config.get("required_validations", []):
        val_fct(file_path)

    content_type = asset_config["content_type"]

    if dry_run:
        L.info(f"Asset '{asset_label}': DRY RUN (not registered)")
        return None

    if registered_circuit is None:
        msg = "registered_circuit is required when dry_run is False!"
        raise ValueError(msg)

    # Upload from local file system
    if is_dir:
        files_in_dir = {
            str(path.relative_to(file_path)): path
            for path in file_path.rglob("*")
            if path.is_file()
        }
        # Filter out .DS_Store files
        num_ignored = sum(1 for f in files_in_dir if ".ds_store" in f.lower())
        if num_ignored > 0:
            L.warning(f"{num_ignored} '.DS_Store' file(s) found in '{file_path}' - ignoring")
        files_in_dir = {k: v for k, v in files_in_dir.items() if ".ds_store" not in k.lower()}
        asset = client.upload_directory(
            label=asset_label,  # ty:ignore[invalid-argument-type]
            name=asset_label,
            entity_id=registered_circuit.id,
            entity_type=models.Circuit,
            paths=files_in_dir,  # ty:ignore[invalid-argument-type]
        )
    else:
        asset = client.upload_file(
            asset_label=asset_label,  # ty:ignore[invalid-argument-type]
            entity_id=registered_circuit.id,
            entity_type=models.Circuit,
            file_path=file_path,
            file_content_type=content_type,
        )
    L.info(f"'{asset_label}' asset uploaded under ID {asset.id}")
    return asset
