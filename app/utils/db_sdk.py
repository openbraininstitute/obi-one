from datetime import UTC, datetime
from uuid import UUID

from entitysdk import Client
from entitysdk.models import Entity
from entitysdk.models.activity import Activity
from entitysdk.types import ExecutorType

from app.logger import L


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
