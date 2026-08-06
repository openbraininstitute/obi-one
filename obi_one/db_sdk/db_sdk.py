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
from entitysdk.models.core import Identifiable
from entitysdk.types import ActivityStatus, AssetLabel, ContentType, ExecutorType, TaskActivityType

from obi_one.core.exception import OBIONEError
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger(__name__)


def get_identifiable[T: Identifiable](
    *, client: Client, identifiable_id: UUID, identifiable_type: type[T]
) -> T:
    resource = client.get_entity(entity_id=identifiable_id, entity_type=identifiable_type)

    if resource.id is None:
        msg = f"Model {identifiable_type} has no ID"
        raise OBIONEError(msg)

    return resource


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
    from entitysdk.utils.filesystem import create_dir  # ruff: ignore[import-outside-top-level]

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
    """Return ``{recording_id: [protocol_class_name, ...]}`` for each recording.

    Reads the stimulus names from each ``ElectricalCellRecording`` entity (no NWB
    download) and maps them to the matching ``Protocol`` subclass name via
    ``protocol_class_name_for``. Stimuli with no matching protocol are dropped.
    """
    from entitysdk.models import ElectricalCellRecording  # ruff: ignore[import-outside-top-level]

    from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long, import-outside-top-level]
        protocol_class_name_for,
    )

    by_recording: dict[str, list[str]] = {}
    for rid in recording_ids:
        entity = db_client.get_entity(
            entity_id=rid,  # ty:ignore[invalid-argument-type]
            entity_type=ElectricalCellRecording,
        )
        stimuli = entity.stimuli or []
        class_names = {
            class_name
            for s in stimuli
            if s.name and (class_name := protocol_class_name_for(s.name)) is not None
        }
        by_recording[rid] = sorted(class_names)
    return by_recording


def get_recording_amplitudes(
    recording_ids: list[str],
    db_client: Client,
) -> dict[str, list[float]]:
    """Return ``{protocol_class_name: [step_amplitude_nA, ...]}`` unioned across recordings.

    Unlike protocol names, amplitudes are not stored on the entity, so each
    ``ElectricalCellRecording``'s NWB asset is downloaded and its per-protocol step
    amplitudes (nA) are estimated with ``read_amplitudes_from_nwb``. Results are then
    keyed by the matching ``Protocol`` subclass name (via ``protocol_class_name_for``)
    so they align with :func:`get_recording_protocols`; stimuli with no matching
    protocol are dropped.
    """
    import tempfile  # ruff: ignore[import-outside-top-level]

    from entitysdk.models import ElectricalCellRecording  # ruff: ignore[import-outside-top-level]

    from obi_one.scientific.library.electrical_cell_recording_properties import (  # ruff: ignore[import-outside-top-level]
        read_amplitudes_from_nwb,
    )
    from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long, import-outside-top-level]
        protocol_class_name_for,
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
                selection={"content_type": ContentType.application_nwb, "label": AssetLabel.nwb},
                output_path=Path(tmp),
            ).one()
            per_protocol = read_amplitudes_from_nwb(Path(asset.path), protocol_names)
        for raw_name, amplitudes in per_protocol.items():
            class_name = protocol_class_name_for(raw_name)
            if class_name is not None:
                combined.setdefault(class_name, set()).update(amplitudes)
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
    from entitysdk.utils.filesystem import create_dir  # ruff: ignore[import-outside-top-level]

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


def _asset_label_value(label: object) -> str:
    """Normalize an asset label (enum or str) to its string value."""
    return str(getattr(label, "value", label))


def _assets_with_label(entity: models.Circuit, asset_label: str) -> list[Asset]:
    """Return all assets on the entity that match ``asset_label``."""
    return [
        asset for asset in (entity.assets or []) if _asset_label_value(asset.label) == asset_label
    ]


def _delete_assets_with_label(
    client: Client, registered_circuit: models.Circuit, asset_label: str
) -> None:
    """Delete all assets with ``asset_label`` on the circuit (in-memory + remote)."""
    for asset in _assets_with_label(registered_circuit, asset_label):
        client.delete_asset(
            entity_id=registered_circuit.id,
            entity_type=models.Circuit,
            asset_id=asset.id,
        )
        L.info("Deleted existing '%s' asset %s", asset_label, asset.id)
        if registered_circuit.assets is not None:
            registered_circuit.assets = [a for a in registered_circuit.assets if a.id != asset.id]


def _upload_or_replace_file(
    client: Client,
    registered_circuit: models.Circuit,
    *,
    asset_label: str,
    file_path: Path,
    file_content_type: str,
    transfer_config: MultipartUploadTransferConfig | None = None,
) -> Asset:
    """Upload a file asset, replacing any existing asset with the same label.

    Uses ``update_asset_file`` (delete + re-upload) when a single existing asset
    is found and no custom transfer config is required. Otherwise deletes any
    matching assets and uploads fresh.
    """
    existing = _assets_with_label(registered_circuit, asset_label)

    if transfer_config is None and len(existing) == 1:
        asset = client.update_asset_file(
            entity_id=registered_circuit.id,
            entity_type=models.Circuit,
            asset_id=existing[0].id,
            file_path=file_path,
            file_content_type=file_content_type,  # ty:ignore[invalid-argument-type]
        )
        L.info("'%s' asset replaced under asset ID %s", asset_label, asset.id)
        return asset

    # Prefer update_asset_file above; when transfer_config is set (e.g. multipart
    # compressed uploads) we delete + upload_file ourselves because
    # update_asset_file does not accept transfer_config.
    if existing:
        _delete_assets_with_label(client, registered_circuit, asset_label)

    asset = client.upload_file(
        entity_id=registered_circuit.id,
        entity_type=models.Circuit,
        file_path=file_path,
        file_content_type=file_content_type,  # ty:ignore[invalid-argument-type]
        asset_label=asset_label,  # ty:ignore[invalid-argument-type]
        transfer_config=transfer_config,
    )
    L.info("'%s' asset uploaded under asset ID %s", asset_label, asset.id)
    return asset


def _upload_or_replace_directory(
    client: Client,
    registered_circuit: models.Circuit,
    *,
    asset_label: str,
    name: str,
    paths: dict,
) -> Asset:
    """Upload a directory asset, replacing any existing asset with the same label.

    entitysdk has no ``update_asset_directory``; this mirrors ``update_asset_file``
    by deleting matching assets first, then uploading.
    """
    if _assets_with_label(registered_circuit, asset_label):
        _delete_assets_with_label(client, registered_circuit, asset_label)

    asset = client.upload_directory(
        label=asset_label,  # ty:ignore[invalid-argument-type]
        name=name,
        entity_id=registered_circuit.id,
        entity_type=models.Circuit,
        paths=paths,
    )
    L.info("'%s' asset uploaded under asset ID %s", asset_label, asset.id)
    return asset


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
