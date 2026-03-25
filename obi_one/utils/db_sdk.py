import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from entitysdk import Client, MultipartUploadTransferConfig, models
from entitysdk.models import Entity
from entitysdk.models.activity import Activity
from entitysdk.models.asset import Asset
from entitysdk.types import AssetLabel, ExecutorType

from obi_one.utils.io import convert_image_to_webp

L = logging.getLogger(__name__)


def get_entity_asset_by_label(*, client: Client, config: Entity, asset_label: AssetLabel) -> Asset:
    """Determines the asset ID of the JSON config asset."""
    return client.select_assets(entity=config, selection={"label": asset_label}).one()


def create_activity(
    *,
    client: Client,
    activity_type: type[Activity],
    activity_status: str = "created",  # TODO: Use ActivityStatus when available
    used: list[Entity],
) -> Activity:
    """Creates and registers an activity of the given type."""
    activity = activity_type(
        start_time=datetime.now(UTC),
        used=used,
        status=activity_status,
        authorized_public=False,
    )
    activity = client.register_entity(activity)
    L.info(f"Activity {activity.id} of type '{activity_type.__name__}' created")
    return activity


def update_activity_status(
    *,
    client: Client,
    activity_id: UUID,
    activity_type: type[Activity],
    status: str,
) -> Activity:
    """Updates the activity by setting a new status."""
    return client.update_entity(
        entity_id=activity_id,
        entity_type=activity_type,
        attrs_or_entity={"status": status},
    )


def update_activity_executor(
    *,
    client: Client,
    activity_id: UUID,
    activity_type: type[Activity],
    execution_id: UUID,
    executor: ExecutorType,
) -> Activity:
    return client.update_entity(
        entity_id=activity_id,
        entity_type=activity_type,
        attrs_or_entity={
            "executor": executor,
            "execution_id": str(execution_id),
        },
    )


def get_activity_status(
    client: Client,
    activity_id: UUID,
    activity_type: type[Activity],
) -> str:
    """Return the current status of a given execution activity."""
    return client.get_entity(
        entity_id=activity_id,
        entity_type=activity_type,
    ).status


def add_circuit_folder_asset(
    client: Client, circuit_path: Path, registered_circuit: models.Circuit
) -> models.Asset:
    """Upload a circuit folder directory asset to a registered circuit entity."""
    asset_label = "sonata_circuit"
    circuit_folder = circuit_path.parent
    if not circuit_folder.is_dir():
        msg = "Circuit folder does not exist!"
        raise FileNotFoundError(msg)

    # Collect circuit files
    circuit_files = {
        str(path.relative_to(circuit_folder)): path
        for path in circuit_folder.rglob("*")
        if path.is_file()
    }
    L.info(f"{len(circuit_files)} files in '{circuit_folder}'")
    if "circuit_config.json" not in circuit_files:
        msg = "Circuit config file not found in circuit folder!"
        raise FileNotFoundError(msg)
    if "node_sets.json" not in circuit_files:
        msg = "Node sets file not found in circuit folder!"
        raise FileNotFoundError(msg)

    # Upload asset
    directory_asset = client.upload_directory(
        label=asset_label,
        name=asset_label,
        entity_id=registered_circuit.id,
        entity_type=models.Circuit,
        paths=circuit_files,
    )
    L.info(f"'{asset_label}' asset uploaded under asset ID {directory_asset.id}")
    return directory_asset


def add_compressed_circuit_asset(
    client: Client, compressed_file: Path, registered_circuit: models.Circuit
) -> models.Asset:
    """Upload a compressed circuit file asset to a registered circuit entity."""
    asset_label = "compressed_sonata_circuit"

    if not compressed_file.exists():
        msg = f"Compressed circuit file '{compressed_file}' does not exist!"
        raise FileNotFoundError(msg)

    # Upload compressed file asset
    transfer_config = MultipartUploadTransferConfig()
    compressed_asset = client.upload_file(
        entity_id=registered_circuit.id,
        entity_type=models.Circuit,
        file_path=compressed_file,
        file_content_type="application/gzip",
        asset_label=asset_label,
        transfer_config=transfer_config,
    )
    L.info(f"'{asset_label}' asset uploaded under asset ID {compressed_asset.id}")
    return compressed_asset


def add_connectivity_matrix_asset(
    client: Client, matrix_dir: Path, registered_circuit: models.Circuit
) -> models.Asset:
    """Upload connectivity matrix directory asset to a registered circuit entity."""
    asset_label = "circuit_connectivity_matrices"

    if not matrix_dir.is_dir():
        msg = f"Connectivity matrix directory '{matrix_dir}' does not exist!"
        raise FileNotFoundError(msg)

    # Collect matrix files
    matrix_files = {
        str(path.relative_to(matrix_dir)): path for path in matrix_dir.rglob("*") if path.is_file()
    }
    L.info(f"{len(matrix_files)} files in '{matrix_dir}'")

    # Upload directory asset
    matrix_asset = client.upload_directory(
        label=asset_label,
        name=asset_label,
        entity_id=registered_circuit.id,
        entity_type=models.Circuit,
        paths=matrix_files,
    )
    L.info(f"'{asset_label}' asset uploaded under asset ID {matrix_asset.id}")
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
    asset_label_map = {
        "node_stats": ("node_stats", "webp"),
        "small_adj_and_stats": ("network_stats_a", "webp"),
        "small_network_in_2D": ("network_stats_b", "webp"),
        "network_global_stats": ("network_stats_a", "webp"),
        "network_pathway_stats": ("network_stats_b", "webp"),
        "circuit_visualization": ("circuit_visualization", "webp"),
        "simulation_designer_image": ("simulation_designer_image", "png"),
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
        plot_asset = client.upload_file(
            entity_id=registered_circuit.id,
            entity_type=models.Circuit,
            file_path=file_path,
            file_content_type=f"image/{fmt}",
            asset_label=asset_label,
        )
        L.info(f"'{asset_label}' asset uploaded under asset ID {plot_asset.id}")
        plot_assets.append(plot_asset)
    return plot_assets
