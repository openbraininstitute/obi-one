import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from entitysdk import Client, models
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
