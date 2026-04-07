import logging

from entitysdk import Client

from obi_one.core.task import Task
from obi_one.scientific.tasks.e_model_optimization.config import EModelOptimizationSingleConfig

L = logging.getLogger(__name__)


class EModelOptimizationTask(Task):
    config: EModelOptimizationSingleConfig

    def execute(
        self,
        *,
        db_client: Client = None,
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,
    ) -> None:
        execution_activity = EModelOptimizationTask._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )

        # self.config.initialize.morphology...

        # self.