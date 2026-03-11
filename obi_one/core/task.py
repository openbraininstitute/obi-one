import abc
import logging

from entitysdk import Client
from entitysdk.models import TaskActivity

from obi_one.core.base import OBIBaseModel

L = logging.getLogger(__name__)


class Task(OBIBaseModel, abc.ABC):
    @staticmethod
    def _get_execution_activity(
        db_client: Client = None,
        execution_activity_id: str | None = None,
    ) -> TaskActivity | None:
        """Returns the TaskAcitivity.

        Such activity is expected to be created and managed externally.
        """
        if db_client and execution_activity_id:
            execution_activity = db_client.get_entity(
                entity_type=TaskActivity, entity_id=execution_activity_id
            )
        else:
            execution_activity = None
        return execution_activity

    @staticmethod
    def _update_execution_activity(
        db_client: Client = None,
        execution_activity: TaskActivity | None = None,
        generated: list[str] | None = None,
    ) -> TaskActivity | None:
        """Updates a TaskActivity after task completion.

        Registers only the generated circuit ID. Other updates (status,
        end time, executor, etc) are expected to be managed externally.
        """
        if db_client and execution_activity and generated:
            upd_dict = {"generated_ids": generated}
            upd_entity = db_client.update_entity(
                entity_id=execution_activity.id,
                entity_type=TaskActivity,
                attrs_or_entity=upd_dict,
            )
            L.info("TaskActivity UPDATED")
        else:
            upd_entity = None
        return upd_entity
