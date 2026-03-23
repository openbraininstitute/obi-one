import logging
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from entitysdk import Client
from entitysdk.models import Entity, TaskActivity, TaskConfig
from entitysdk.models.activity import Activity
from entitysdk.models.asset import Asset
from entitysdk.types import ActivityStatus, AssetLabel, ContentType, ExecutorType, TaskActivityType

L = logging.getLogger(__name__)


def get_entity_asset_by_label(*, client: Client, config: Entity, asset_label: AssetLabel) -> Asset:
    """Determines the asset ID of the JSON config asset."""
    return client.select_assets(entity=config, selection={"label": asset_label}).one()


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


def create_generic_activity(
    *,
    client: Client,
    config: list[Entity],
    task_activity_type: TaskActivityType,
    activity_status: ActivityStatus = ActivityStatus.created,
) -> Activity:
    """Creates and registers a generic task activity."""
    activity = TaskActivity(
        task_activity_type=task_activity_type,
        start_time=datetime.now(UTC),
        used=config,
        status=activity_status,
        authorized_public=False,
    )
    activity = client.register_entity(activity)
    L.info(
        f"Generic task activity {activity.id} of type '{TaskActivity.__name__}' of"
        f" task_activity_type '{task_activity_type}' created"
    )
    return activity


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


def upload_task_config_asset(
    *,
    client: Client,
    entity: Entity,
    file_path: Path,
) -> Asset:
    """Uploads the given task configuration as an asset and returns it."""
    L.info("-- Upload task_config asset for campaign TaskConfig")
    asset = client.upload_file(
        entity_id=entity.id,
        entity_type=TaskConfig,
        file_path=file_path,
        file_content_type=ContentType.json,
        asset_label=AssetLabel.task_config,
    )
    return asset
