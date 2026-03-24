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


def register_task_config_entity(
    *,
    client: Client,
    campaign_name: str,
    campaign_description: str,
    campaign_task_config_type: str,
    multiple_value_parameters_dictionary: dict,
    input_entity_ids: list[UUID],
) -> TaskConfig:
    """Registers a TaskConfig entity for the given campaign and returns it."""
    L.info("-- Create campaign TaskConfig entity")
    campaign_task_config = client.register_entity(
        TaskConfig(
            name=campaign_name,
            description=campaign_description,
            task_config_type=campaign_task_config_type,
            meta={"scan_parameters": multiple_value_parameters_dictionary},
            inputs=[Entity(id=entity_id) for entity_id in input_entity_ids],
        )
    )
    return campaign_task_config


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


def register_campaign_task_config_entity_and_upload_asset(
    *,
    client: Client,
    campaign_name: str,
    campaign_description: str,
    campaign_task_config_type: str,
    multiple_value_parameters_dictionary: dict,
    input_entity_ids: list[UUID],
    task_config_file_path: Path,
) -> tuple[TaskConfig, Asset]:
    """Registers a TaskConfig entity for the given campaign, uploads the task config asset."""
    task_config_entity = register_task_config_entity(
        client=client,
        campaign_name=campaign_name,
        campaign_description=campaign_description,
        campaign_task_config_type=campaign_task_config_type,
        multiple_value_parameters_dictionary=multiple_value_parameters_dictionary,
        input_entity_ids=input_entity_ids,
    )
    asset = upload_task_config_asset(
        client=client,
        entity=task_config_entity,
        file_path=task_config_file_path,
    )
    return task_config_entity, asset


def register_coordinate_task_config_entity_and_upload_asset(
    *,
    client: Client,
    name: str,
    description: str,
    task_config_type: str,
    multiple_value_parameters_dictionary: dict,
    input_entity_ids: list[UUID],
    task_config_file_path: Path,
) -> tuple[TaskConfig, Asset]:
    """Registers a TaskConfig entity for the given campaign, uploads the task config asset."""
    task_config_entity = register_task_config_entity(
        client=client,
        campaign_name=name,
        campaign_description=description,
        campaign_task_config_type=task_config_type,
        multiple_value_parameters_dictionary=multiple_value_parameters_dictionary,
        input_entity_ids=input_entity_ids,
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
