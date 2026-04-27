import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from entitysdk import Client, MultipartUploadTransferConfig, models
from entitysdk.exception import EntitySDKError
from entitysdk.models import Entity, TaskActivity, TaskConfig
from entitysdk.models.activity import Activity
from entitysdk.models.asset import Asset
from entitysdk.types import ActivityStatus, AssetLabel, ContentType, ExecutorType, TaskActivityType

from obi_one.core.exception import OBIONEError
from obi_one.utils.io import convert_image_to_webp

L = logging.getLogger(__name__)


def get_entity_asset_by_label(*, client: Client, config: Entity, asset_label: AssetLabel) -> Asset:
    """Determines the asset ID of the JSON config asset."""
    try:
        return client.select_assets(entity=config, selection={"label": asset_label}).one()
    except EntitySDKError as e:
        msg = (
            f"Could not find asset with label '{asset_label}' "
            f"in Config(id={config.id}, type=config.type)\n"
            f"Assets: {config.assets}",
        )
        raise OBIONEError(msg) from e


def get_task_config_asset(*, client: Client, config: Entity) -> Asset:
    """Return task config asset from entity."""
    return get_entity_asset_by_label(
        client=client, config=config, asset_label=AssetLabel.task_config
    )


def create_activity(
    *,
    client: Client,
    activity_type: type[Activity],
    activity_status: ActivityStatus = ActivityStatus.created,
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


def select_asset_content(
    *,
    client: Client,
    entity: Entity | None = None,
    entity_id: UUID | None = None,
    entity_type: type[Entity] | None = None,
    selection: dict,
) -> bytes:
    """Select an asset from an entity and fetch its content."""
    if entity is None:
        entity = client.get_entity(entity_id=entity_id, entity_type=entity_type)
    asset = client.select_assets(
        entity=entity,
        selection=selection,
    ).one()
    return client.fetch_content(
        entity_id=entity.id,
        entity_type=type(entity),
        asset_or_id=asset,
    )


def select_json_asset_content(
    *,
    client: Client,
    entity: Entity | None = None,
    entity_id: UUID | None = None,
    entity_type: type[Entity] | None = None,
    selection: dict,
) -> dict:
    """Select an asset from the entity and fetch its content."""
    bytes_content = select_asset_content(
        client=client,
        entity=entity,
        entity_id=entity_id,
        entity_type=entity_type,
        selection=selection | {"content_type": ContentType.application_json},
    )
    return json.loads(bytes_content)


def create_generic_activity(
    *,
    client: Client,
    used: list[Entity],
    activity_type: TaskActivityType,
    activity_status: ActivityStatus = ActivityStatus.created,
    generated: list[Entity] | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> Activity:
    """Creates and registers a generic task activity."""
    activity = TaskActivity(
        task_activity_type=activity_type,
        start_time=start_time or datetime.now(UTC),
        end_time=end_time,
        used=used,
        generated=generated,
        status=activity_status,
        authorized_public=False,
    )
    activity = client.register_entity(activity)
    L.info(f"Generic task activity {activity.id} of task_activity_type '{activity_type}' created")
    return activity


def finalize_activity(
    *,
    client: Client,
    activity_id: UUID,
    activity_type: type[Activity],
    status: Literal[ActivityStatus.done, ActivityStatus.error, ActivityStatus.cancelled],
    end_time: datetime | None = None,
) -> Activity:
    """Finalize activity status and end time."""
    return client.update_entity(
        entity_id=activity_id,
        entity_type=activity_type,
        attrs_or_entity={
            "status": status,
            "end_time": end_time or datetime.now(UTC),
        },
    )


def update_activity_status(
    *,
    client: Client,
    activity_id: UUID,
    activity_type: type[Activity],
    status: ActivityStatus,
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


def register_task_config_entity(
    *,
    client: Client,
    name: str,
    description: str,
    task_config_type: str,
    multiple_value_parameters_dictionary: dict,
    input_entities: list[Entity],
    task_config_generator_id: UUID | None = None,
) -> TaskConfig:
    """Registers a TaskConfig entity for the given task_config_type and returns it."""
    L.info("-- Create TaskConfig entity")
    task_config = client.register_entity(
        TaskConfig(
            name=name,
            description=description,
            task_config_type=task_config_type,
            meta=multiple_value_parameters_dictionary,
            inputs=input_entities,
            task_config_generator_id=task_config_generator_id,
        )
    )
    return task_config


def upload_task_config_asset(
    *,
    client: Client,
    entity: Entity,
    file_path: Path,
) -> Asset:
    """Uploads the given task configuration as an asset and returns it."""
    L.info("-- Upload task_config asset for TaskConfig")
    asset = client.upload_file(
        entity_id=entity.id,
        entity_type=TaskConfig,
        file_path=file_path,
        file_content_type=ContentType.application_json,
        asset_label=AssetLabel.task_config,
    )
    return asset


def register_task_config_with_asset(
    *,
    client: Client,
    name: str,
    description: str,
    task_config_type: str,
    multiple_value_parameters_dictionary: dict,
    input_entities: list[UUID],
    task_config_file_path: Path,
    task_config_generator_id: UUID | None = None,
) -> tuple[TaskConfig, Asset]:
    """Registers a TaskConfig entity for the task_config_type, uploads the task config asset."""
    L.info(f"-- Register TaskConfig type: {task_config_type} and task_config asset")
    task_config_entity = register_task_config_entity(
        client=client,
        name=name,
        description=description,
        task_config_type=task_config_type,
        multiple_value_parameters_dictionary=multiple_value_parameters_dictionary,
        input_entities=input_entities,
        task_config_generator_id=task_config_generator_id,
    )
    asset = upload_task_config_asset(
        client=client,
        entity=task_config_entity,
        file_path=task_config_file_path,
    )
    return task_config_entity, asset


def update_execution_activity_with_generated(
    *,
    client: Client,
    execution_activity_id: UUID,
    generated_ids: list[str],
) -> TaskActivity:
    """Updates the given execution activity by setting the generated circuit ID."""
    entity = client.update_entity(
        entity_id=execution_activity_id,
        entity_type=TaskActivity,
        attrs_or_entity={"generated_ids": generated_ids},
    )
    L.info("TaskActivity updated with generated_ids")
    return entity


def get_execution_activity(
    *,
    client: Client,
    execution_activity_id: UUID,
) -> TaskActivity:
    """Returns the given execution activity."""
    return client.get_entity(
        entity_id=execution_activity_id,
        entity_type=TaskActivity,
    )


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
