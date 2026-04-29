from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.spike_sorting.dispatch.config import AINDEPhysDispatchSingleConfig


class AINDEPhysDispatchTask(Task):
    """SpikeSortingPreprocessing."""

    name: ClassVar[str] = "Multi Electrode Recording Postprocessing"
    description: ClassVar[str] = "Spike sorting preprocessing configuration."

    config: AINDEPhysDispatchSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> str:
        command = self.config.command_line_representation()
        print(command)
        return command
