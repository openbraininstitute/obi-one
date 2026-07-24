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
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.utils.io import convert_image_to_webp

L = logging.getLogger(__name__)

OVERVIEW_IMAGE_NAME = "circuit_visualization"
SIM_DESIGNER_IMAGE_NAME = "simulation_designer_image"


def get_entity_asset_by_label(*, client: Client, config: Entity, asset_label: AssetLabel) -> Asset:
    """Determines the asset ID of the JSON config asset."""
    try:
        return client.select_assets(entity=config, selection={"label": asset_label}).one()
    except EntitySDKError as e:
        msg = (
            f"Could not find asset with label '{asset_label}' "
            f"in Config(id={config.id}, type=config.type)\n"
            f"Assets: {config.assets}"
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


def fetch_asset_by_label(
    *,
    client: Client,
    entity: Entity,
    asset_label: AssetLabel,
    output_path: Path,
) -> Path:
    """Fetch a single asset matching the given label to output_path.

    Uses fetch_assets (checks local data store first).
    Returns the path to the fetched file.
    """
    from entitysdk.utils.filesystem import create_dir  # noqa: PLC0415

    output_dir = create_dir(output_path)
    asset = client.fetch_assets(
        entity,
        selection={"label": asset_label},
        output_path=output_dir,
    ).one()
    return asset.path


def get_recording_protocols(
    recording_ids: list[str],
    db_client: Client,
) -> dict[str, list[str]]:
    """Return ``{recording_id: [protocol_name, ...]}`` for each recording.

    Reads protocol names from the ``stimuli`` field of each
    ``ElectricalCellRecording`` entity — no NWB download required.
    """
    from entitysdk.models import ElectricalCellRecording  # noqa: PLC0415

    by_recording: dict[str, list[str]] = {}
    for rid in recording_ids:
        entity = db_client.get_entity(
            entity_id=rid,  # ty:ignore[invalid-argument-type]
            entity_type=ElectricalCellRecording,
        )
        stimuli = entity.stimuli or []
        by_recording[rid] = sorted({s.name for s in stimuli if s.name})
    return by_recording


def get_recording_amplitudes(
    recording_ids: list[str],
    db_client: Client,
) -> dict[str, list[float]]:
    """Return ``{protocol_name: [step_amplitude_nA, ...]}`` unioned across recordings.

    Unlike protocol names, amplitudes are not stored on the entity, so each
    ``ElectricalCellRecording``'s NWB asset is downloaded and its per-protocol step
    amplitudes (nA) are estimated with ``read_amplitudes_from_nwb``.
    """
    import tempfile  # noqa: PLC0415

    from entitysdk.models import ElectricalCellRecording  # noqa: PLC0415

    from obi_one.scientific.library.electrical_cell_recording_properties import (  # noqa: PLC0415
        read_amplitudes_from_nwb,
    )

    combined: dict[str, set[float]] = {}
    for rid in recording_ids:
        entity = db_client.get_entity(
            entity_id=rid,  # ty:ignore[invalid-argument-type]
            entity_type=ElectricalCellRecording,
        )
        protocol_names = sorted({s.name for s in (entity.stimuli or []) if s.name})
        if not protocol_names:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            asset = db_client.fetch_assets(
                entity,
                selection={"content_type": ContentType.application_nwb},
                output_path=Path(tmp),
            ).one()
            per_protocol = read_amplitudes_from_nwb(Path(asset.path), protocol_names)
        for protocol_name, amplitudes in per_protocol.items():
            combined.setdefault(protocol_name, set()).update(amplitudes)
    return {protocol: sorted(values) for protocol, values in combined.items()}


def fetch_directory_asset_by_label(
    *,
    client: Client,
    entity: Entity,
    asset_label: AssetLabel,
    output_path: Path,
) -> Path:
    """Fetch a directory asset matching the given label to output_path.

    Uses fetch_assets (checks local data store first).
    Returns the path to the fetched directory.
    """
    from entitysdk.utils.filesystem import create_dir  # noqa: PLC0415

    output_dir = create_dir(output_path)
    asset = client.fetch_assets(
        entity,
        selection={"label": asset_label, "content_type": ContentType.application_vnd_directory},
        output_path=output_dir,
    ).one()
    return asset.path


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
        entity = client.get_entity(entity_id=entity_id, entity_type=entity_type)  # ty:ignore[invalid-argument-type]
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
            task_config_type=task_config_type,  # ty:ignore[invalid-argument-type]
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
        input_entities=input_entities,  # ty:ignore[invalid-argument-type]
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
        label=asset_label,  # ty:ignore[invalid-argument-type]
        name=asset_label,
        entity_id=registered_circuit.id,
        entity_type=models.Circuit,
        paths=circuit_files,  # ty:ignore[invalid-argument-type]
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
        file_content_type="application/gzip",  # ty:ignore[invalid-argument-type]
        asset_label=asset_label,  # ty:ignore[invalid-argument-type]
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
        label=asset_label,  # ty:ignore[invalid-argument-type]
        name=asset_label,
        entity_id=registered_circuit.id,
        entity_type=models.Circuit,
        paths=matrix_files,  # ty:ignore[invalid-argument-type]
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
        OVERVIEW_IMAGE_NAME: ("circuit_visualization", "webp"),
        SIM_DESIGNER_IMAGE_NAME: ("simulation_designer_image", "png"),
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
            file_content_type=f"image/{fmt}",  # ty:ignore[invalid-argument-type]
            asset_label=asset_label,  # ty:ignore[invalid-argument-type]
        )
        L.info(f"'{asset_label}' asset uploaded under asset ID {plot_asset.id}")
        plot_assets.append(plot_asset)
    return plot_assets


def resolve_circuit(
    circuit: Circuit | CircuitFromID,
    *,
    db_client: Client,
    entity_cache: bool,
    cache_root: Path,
    temp_dir: Path,
) -> tuple[Circuit, models.Circuit | None]:
    """Resolve a circuit object into a staged local circuit.

    Handles both local Circuit instances and CircuitFromID references that
    need to be staged from entitycore.

    Args:
        circuit: A Circuit instance (local) or CircuitFromID (remote).
        db_client: The entitycore SDK client.
        entity_cache: If True, stage into a persistent cache directory under
            cache_root; otherwise stage into temp_dir.
        cache_root: Root path for the entity cache (e.g., scan_output_root).
        temp_dir: Temporary directory path to use when entity_cache is False.

    Returns:
        Tuple of (resolved Circuit, circuit entity or None).
    """
    if isinstance(circuit, Circuit):
        L.info("Circuit is a local Circuit instance.")
        return circuit, None

    if isinstance(circuit, CircuitFromID):
        L.info("Circuit is a CircuitFromID instance.")
        circuit_id = circuit.id_str

        if entity_cache:
            L.info("Use entity cache")
            dest_dir = cache_root / "entity_cache" / "sonata_circuit" / circuit_id
        else:
            dest_dir = temp_dir / "sonata_circuit"

        staged_circuit = circuit.stage_circuit(
            db_client=db_client, dest_dir=dest_dir, entity_cache=entity_cache
        )
        circuit_entity = circuit.entity(db_client=db_client)
        return staged_circuit, circuit_entity  # ty:ignore[invalid-return-type]

    msg = f"Unsupported circuit type: {type(circuit)}"
    raise OBIONEError(msg)
