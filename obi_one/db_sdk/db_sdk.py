import json
import logging
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from entitysdk import Client
from entitysdk.exception import EntitySDKError
from entitysdk.models import ElectricalCellRecording, Entity, TaskActivity, TaskConfig
from entitysdk.models.activity import Activity
from entitysdk.models.asset import Asset
from entitysdk.models.core import Identifiable
from entitysdk.types import (
    ActivityStatus,
    AssetLabel,
    ContentType,
    ExecutorType,
    FetchFileStrategy,
    TaskActivityType,
)
from entitysdk.utils.filesystem import create_dir
from pydantic import ValidationError

from obi_one.core.exception import OBIONEError
from obi_one.scientific.library.recording_summary import (
    RecordingSummary,
    compute_recording_summary,
)

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


def get_task_config_asset_content(*, client: Client, config: TaskConfig) -> dict:
    """Return task config JSON as a dict."""
    return select_json_asset_content(
        client=client, entity=config, selection={"label": AssetLabel.task_config}
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
    strategy: FetchFileStrategy = FetchFileStrategy.link_or_download,
) -> Path:
    """Fetch a single asset matching the given label to output_path.

    Uses fetch_assets (checks local data store first).
    Returns the path to the fetched file.
    """
    output_dir = create_dir(output_path)
    asset = client.fetch_assets(
        entity,
        selection={"label": asset_label},
        output_path=output_dir,
        strategy=strategy,
    ).one()
    return asset.path


def get_electrical_cell_recordings(
    recording_ids: list[str],
    db_client: Client,
) -> dict[str, ElectricalCellRecording]:
    """Return ``{recording_id: ElectricalCellRecording}``, one request per recording."""
    return {
        rid: db_client.get_entity(UUID(rid), entity_type=ElectricalCellRecording)
        for rid in recording_ids
    }


def recording_protocol_classes(recording: ElectricalCellRecording) -> list[str]:
    """Return the ``Protocol`` subclass names of a recording's stimuli, sorted.

    Reads the stimulus names from the entity (no NWB download) and maps them with
    ``protocol_class_name_for``. Stimuli with no matching protocol are dropped.
    """
    from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long, import-outside-top-level]
        protocol_class_name_for,
    )

    return sorted(
        {
            class_name
            for s in recording.stimuli or []
            if s.name and (class_name := protocol_class_name_for(s.name)) is not None
        }
    )


def get_recording_protocols(
    recording_ids: list[str],
    db_client: Client,
) -> dict[str, list[str]]:
    """Return ``{recording_id: [protocol_class_name, ...]}`` for each recording."""
    recordings = get_electrical_cell_recordings(recording_ids, db_client)
    return {rid: recording_protocol_classes(recording) for rid, recording in recordings.items()}


def fetch_recording_summary(
    client: Client,
    recording: ElectricalCellRecording,
) -> RecordingSummary | None:
    """The recording's stored ``recording_summary`` asset, if any.

    Returns ``None`` when the recording has no such asset or its content fails
    validation. When several exist (entitycore does not prevent it), the last
    one listed is used.
    """
    assets = [a for a in recording.assets or [] if a.label == AssetLabel.recording_summary]
    if not assets:
        return None
    if len(assets) > 1:
        L.warning("Recording %s has %d recording summaries", recording.id, len(assets))
    content = client.fetch_content(
        entity_id=recording.id,
        entity_type=ElectricalCellRecording,
        asset_or_id=assets[-1],
    )
    try:
        return RecordingSummary.model_validate_json(content)
    except ValidationError as e:
        L.warning("Invalid recording summary %s of %s: %s", assets[-1].id, recording.id, e)
        return None


def compute_recording_summary_from_nwb(
    client: Client,
    recording: ElectricalCellRecording,
) -> RecordingSummary | None:
    """Download the recording's NWB asset and compute its summary (not uploaded).

    Returns ``None`` when the recording has no NWB asset.
    """
    if not any(a.label == AssetLabel.nwb for a in recording.assets or []):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        asset = client.fetch_assets(
            recording,
            selection={"content_type": ContentType.application_nwb, "label": AssetLabel.nwb},
            output_path=Path(tmp),
        ).one()
        return compute_recording_summary(Path(asset.path))


def get_recording_summary(
    client: Client,
    recording: ElectricalCellRecording,
) -> RecordingSummary | None:
    """The recording's stored summary, else one computed from its NWB file."""
    summary = fetch_recording_summary(client, recording)
    if summary is None:
        summary = compute_recording_summary_from_nwb(client, recording)
    return summary


def amplitudes_by_protocol_class(
    summaries: Mapping[str, RecordingSummary | None],
) -> dict[str, list[float]]:
    """Return ``{protocol_class_name: [amp_nA, ...]}`` unioned across recordings.

    Uses each protocol's ``amp`` (the amplitude extraction matches targets on).
    Protocols are keyed by the matching ``Protocol`` subclass name (via
    ``protocol_class_name_for``), so they align with
    :func:`recording_protocol_classes`; protocols with no match are dropped.
    """
    from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long, import-outside-top-level]
        protocol_class_name_for,
    )

    combined: dict[str, set[float]] = {}
    for summary in summaries.values():
        if summary is None:
            continue
        for raw_name, protocol in summary.protocols.items():
            class_name = protocol_class_name_for(raw_name)
            if class_name is not None:
                combined.setdefault(class_name, set()).update(protocol.amp)
    return {name: sorted(values) for name, values in combined.items()}


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
        if entity_id is None or entity_type is None:
            msg = "entity_id and entity_type are required when entity is not provided"
            raise ValueError(msg)
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
