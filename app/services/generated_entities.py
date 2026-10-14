"""What happens to the entities a task created, once its job succeeds.

A task definition lists the entity types it registers (``generated_entity_types``). For each
type that has a handler here, the job gets the handler's task options plus a success callback,
and the callback runs the handler on the entities of that type.
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import entitysdk.client
import httpx
from entitysdk.models import Entity
from entitysdk.types import EntityType

from app.errors import internal_error
from app.schemas.task import LaunchableTaskDefinition
from app.services.circuit_launch import validate_draft_circuits
from obi_one.db_sdk.db_sdk import get_execution_activity
from obi_one.db_sdk.registration.circuit.lifecycle import CircuitValidationMode


class GeneratedEntitiesHandle(Protocol):
    """Signature of a handler: it runs on the generated entities of one type."""

    def __call__(
        self,
        *,
        entities: list[Entity],
        db_client: entitysdk.client.Client,
        ls_client: httpx.Client,
        compute_cell: str,
    ) -> None: ...


@dataclass(frozen=True)
class GeneratedEntityHandler:
    """Handler for one generated entity type.

    Attributes:
        task_options: Fields set on the task when the job is launched (``--task_option
            KEY=VALUE``), so the task registers its entities the way ``handle`` expects.
        handle: Called with the entities of this type that the task activity generated.
    """

    task_options: dict[str, str]
    handle: GeneratedEntitiesHandle


GENERATED_ENTITY_HANDLERS: dict[EntityType, GeneratedEntityHandler] = {
    EntityType.circuit: GeneratedEntityHandler(
        task_options={"circuit_validation_mode": CircuitValidationMode.async_launch},
        handle=validate_draft_circuits,
    ),
}


def get_generated_entity_handlers(
    task_definition: LaunchableTaskDefinition,
) -> dict[EntityType, GeneratedEntityHandler]:
    """Return the handlers for the entity types the task definition lists, keyed by type."""
    return {
        entity_type: GENERATED_ENTITY_HANDLERS[entity_type]
        for entity_type in task_definition.generated_entity_types
        if entity_type in GENERATED_ENTITY_HANDLERS
    }


def handle_generated_entities(
    *,
    task_definition: LaunchableTaskDefinition,
    activity_id: UUID,
    db_client: entitysdk.client.Client,
    ls_client: httpx.Client,
    compute_cell: str,
) -> None:
    """Run the task's handlers on the entities the activity generated.

    The callback is only registered for task definitions that have a handler, so a definition
    without one is an internal error.

    Args:
        task_definition: Definition of the task whose job succeeded.
        activity_id: ID of the task's execution activity.
        db_client: EntitySDK client with the task's project context.
        ls_client: Launch-system HTTP client.
        compute_cell: Compute cell for the jobs the handlers start (from the virtual lab).
    """
    handlers = get_generated_entity_handlers(task_definition)
    if not handlers:
        msg = f"Task type {task_definition.task_type!r} has no generated-entity handler."
        raise internal_error(msg)
    activity = get_execution_activity(client=db_client, execution_activity_id=activity_id)
    generated = activity.generated or []
    for entity_type, handler in handlers.items():
        handler.handle(
            entities=[entity for entity in generated if entity.type == entity_type],
            db_client=db_client,
            ls_client=ls_client,
            compute_cell=compute_cell,
        )
