"""Asset validation and registration for circuits."""

import json
import logging
from pathlib import Path

from entitysdk import Client, MultipartUploadTransferConfig, models
from entitysdk.types import AssetLabel

from obi_one.db_sdk.db_sdk import _upload_or_replace_directory, _upload_or_replace_file
from obi_one.utils.io import compressed_archive_filename, convert_image_to_webp

L = logging.getLogger(__name__)

OVERVIEW_IMAGE_NAME = "circuit_visualization"
SIM_DESIGNER_IMAGE_NAME = "simulation_designer_image"

# Canonical name/format for the compressed SONATA circuit asset (a gzip-compressed tar).
COMPRESSED_CIRCUIT_NAME = "circuit"
COMPRESSED_CIRCUIT_FORMAT = "gz"
COMPRESSED_CIRCUIT_FILENAME = compressed_archive_filename(
    COMPRESSED_CIRCUIT_NAME, COMPRESSED_CIRCUIT_FORMAT
)

# Canonical config filename inside a connectivity-matrix asset directory.
MATRIX_CONFIG_FILENAME = "matrix_config.json"

# Required files inside the main SONATA circuit folder.
SONATA_CIRCUIT_REQUIRED_CONTENTS = ["circuit_config.json", "node_sets.json"]


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

    if MATRIX_CONFIG_FILENAME not in matrix_files:
        msg = f"{MATRIX_CONFIG_FILENAME} missing!"
        raise ValueError(msg)

    with matrix_files[MATRIX_CONFIG_FILENAME].open(encoding="utf-8") as f:
        mat_cfg = json.load(f)

    for pop in mat_cfg:
        for mat in mat_cfg[pop].values():
            mpath = mat["path"]
            if mpath not in matrix_files:
                msg = f"Matrix file '{mpath}' referenced in config but not found!"
                raise ValueError(msg)


def register_sonata_circuit_asset(
    client: Client,
    file_path: Path | None,
    registered_circuit: models.Circuit | None,
    *,
    dry_run: bool,
) -> models.Asset | None:
    """Register the main SONATA circuit folder asset for a circuit entity.

    Validates that the folder exists and contains the required SONATA files before
    registration. Other circuit assets (compressed archive, connectivity matrices,
    images) are registered by their dedicated ``add_*`` helpers.

    Args:
        client: The entitycore SDK client.
        file_path: Path to the SONATA circuit folder. None to skip.
        registered_circuit: The circuit entity to attach the asset to.
        dry_run: If True, perform validation only without registering.

    Returns:
        The registered asset, or None if skipped or dry_run.
    """
    asset_label = AssetLabel.sonata_circuit

    if file_path is None:
        L.info(f"No path for '{asset_label.value}' asset provided - skipping")
        return None

    if not file_path.exists():
        msg = f"File path '{file_path}' does not exist!"
        raise ValueError(msg)

    _check_required_contents(file_path, SONATA_CIRCUIT_REQUIRED_CONTENTS, is_directory=True)

    if dry_run:
        L.info(f"Asset '{asset_label.value}': DRY RUN (not registered)")
        return None

    if registered_circuit is None:
        msg = "registered_circuit is required when dry_run is False!"
        raise ValueError(msg)

    files_in_dir = {
        str(path.relative_to(file_path)): path for path in file_path.rglob("*") if path.is_file()
    }
    # Filter out .DS_Store files
    num_ignored = sum(1 for f in files_in_dir if ".ds_store" in f.lower())
    if num_ignored > 0:
        L.warning(f"{num_ignored} '.DS_Store' file(s) found in '{file_path}' - ignoring")
    files_in_dir = {k: v for k, v in files_in_dir.items() if ".ds_store" not in k.lower()}

    asset = _upload_or_replace_directory(
        client,
        registered_circuit,
        asset_label=asset_label,
        name=asset_label.value,
        paths=files_in_dir,
    )
    L.info(f"'{asset_label.value}' asset uploaded under ID {asset.id}")
    return asset


def add_compressed_circuit_asset(
    client: Client, compressed_file: Path, registered_circuit: models.Circuit
) -> models.Asset:
    """Upload a compressed circuit file asset to a registered circuit entity."""
    asset_label = AssetLabel.compressed_sonata_circuit

    if not compressed_file.exists():
        msg = f"Compressed circuit file '{compressed_file}' does not exist!"
        raise FileNotFoundError(msg)

    # Validate the file is the canonical compressed-circuit archive.
    _check_required_contents(compressed_file, [COMPRESSED_CIRCUIT_FILENAME], is_directory=False)

    # Upload compressed file asset (replace if present)
    transfer_config = MultipartUploadTransferConfig()
    compressed_asset = _upload_or_replace_file(
        client,
        registered_circuit,
        asset_label=asset_label,
        file_path=compressed_file,
        file_content_type="application/gzip",
        transfer_config=transfer_config,
    )
    L.info(f"'{asset_label.value}' asset uploaded under asset ID {compressed_asset.id}")
    return compressed_asset


def add_connectivity_matrix_asset(
    client: Client, matrix_dir: Path, registered_circuit: models.Circuit
) -> models.Asset:
    """Upload connectivity matrix directory asset to a registered circuit entity."""
    asset_label = AssetLabel.circuit_connectivity_matrices

    if not matrix_dir.is_dir():
        msg = f"Connectivity matrix directory '{matrix_dir}' does not exist!"
        raise FileNotFoundError(msg)

    # Validate matrix_config.json exists and all referenced matrix files are present.
    _check_required_contents(matrix_dir, [MATRIX_CONFIG_FILENAME], is_directory=True)
    _check_matrix_folder(matrix_dir)

    # Collect matrix files
    matrix_files = {
        str(path.relative_to(matrix_dir)): path for path in matrix_dir.rglob("*") if path.is_file()
    }
    L.info(f"{len(matrix_files)} files in '{matrix_dir}'")

    # Upload directory asset (replace if present)
    matrix_asset = _upload_or_replace_directory(
        client,
        registered_circuit,
        asset_label=asset_label,
        name=asset_label.value,
        paths=matrix_files,
    )
    L.info(f"'{asset_label.value}' asset uploaded under asset ID {matrix_asset.id}")
    return matrix_asset


def add_image_assets(
    client: Client,
    plot_dir: Path,
    plot_files: list,
    registered_circuit: models.Circuit,
) -> list[models.Asset]:
    """Upload connectivity plot assets to a registered circuit entity.

    Note: Image files will be converted to .webp, if needed.
    """
    # Keys are plot-figure filename stems (not asset labels); values pair the target asset
    # label with the on-disk format.
    asset_label_map = {
        "node_stats": (AssetLabel.node_stats, "webp"),
        "small_adj_and_stats": (AssetLabel.network_stats_a, "webp"),
        "small_network_in_2D": (AssetLabel.network_stats_b, "webp"),
        "network_global_stats": (AssetLabel.network_stats_a, "webp"),
        "network_pathway_stats": (AssetLabel.network_stats_b, "webp"),
        OVERVIEW_IMAGE_NAME: (AssetLabel.circuit_visualization, "webp"),
        SIM_DESIGNER_IMAGE_NAME: (AssetLabel.simulation_designer_image, "png"),
    }
    if not plot_dir.is_dir():
        msg = f"Connectivity plots directory '{plot_dir}' does not exist!"
        raise FileNotFoundError(msg)

    # Upload image file assets (incl. conversion to .webp format if needed)
    plot_assets = []
    for file in plot_files:
        file_path = plot_dir / file
        if not file_path.is_file():
            msg = f"Connectivity plot '{file_path.name}' does not exist!"
            raise FileNotFoundError(msg)
        if file_path.stem not in asset_label_map:
            msg = f"No asset label for plot '{file_path.name}' - SKIPPING!"
            L.warning(msg)
            continue
        asset_label, fmt = asset_label_map[file_path.stem]
        if fmt == "webp":
            file_path = convert_image_to_webp(image_path=file_path)
        if "." + fmt != file_path.suffix:
            msg = f"File format mismatch '{file_path.name}' (.{fmt} required)!"
            raise ValueError(msg)
        plot_asset = _upload_or_replace_file(
            client,
            registered_circuit,
            asset_label=asset_label,
            file_path=file_path,
            file_content_type=f"image/{fmt}",
        )
        L.info(f"'{asset_label.value}' asset uploaded under asset ID {plot_asset.id}")
        plot_assets.append(plot_asset)
    return plot_assets
