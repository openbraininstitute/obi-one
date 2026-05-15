import abc
import logging

from entitysdk import Client
from entitysdk.models import TaskActivity

from obi_one.core.base import OBIBaseModel
from obi_one.utils import db_sdk

L = logging.getLogger(__name__)


class Task(OBIBaseModel, abc.ABC):
    @staticmethod
    def _get_execution_activity(
        db_client: Client | None = None,
        execution_activity_id: str | None = None,
    ) -> TaskActivity | None:
        """Returns the TaskAcitivity.

        Such activity is expected to be created and managed externally.
        """
        execution_activity = None
        if db_client and execution_activity_id:
            execution_activity = db_sdk.get_execution_activity(
                client=db_client,
                execution_activity_id=execution_activity_id,  # ty:ignore[invalid-argument-type]
            )
        return execution_activity

    @staticmethod
    def _update_execution_activity(
        db_client: Client = None,  # ty:ignore[invalid-parameter-default]
        execution_activity: TaskActivity | None = None,
        generated: list[str] | None = None,
    ) -> TaskActivity | None:
        """Updates a TaskActivity after task completion.

        Registers only the generated entity IDs. Other updates (status,
        end time, executor, etc) are expected to be managed externally.
        """
        upd_entity = None
        if db_client and execution_activity and generated:
            upd_entity = db_sdk.update_execution_activity_with_generated(
                client=db_client,
                execution_activity_id=execution_activity.id,  # ty:ignore[invalid-argument-type]
                generated_ids=generated,
            )

        return upd_entity
