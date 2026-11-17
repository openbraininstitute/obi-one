"""Morphology metrics task."""

import logging

import entitysdk

from obi_one.core.exception import OBIONEError
from obi_one.core.task import Task
from obi_one.scientific.library.morphology_metrics import (
    MorphologyMetricsOutput,
)
from obi_one.scientific.tasks.morphology_metrics.config import MorphologyMetricsSingleConfig

L = logging.getLogger(__name__)


class MorphologyMetricsTask(Task):
    config: MorphologyMetricsSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client,
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,  # ruff: ignore[unused-method-argument]
    ) -> MorphologyMetricsOutput:
        try:
            L.info("Running Morphology Metrics...")
            morphology_metrics = MorphologyMetricsOutput.from_morphology(
                self.config.initialize.morphology.neurom_morphology(db_client=db_client)  # ty:ignore[unresolved-attribute]
            )
            L.info(morphology_metrics)

        except Exception as e:
            message = f"Internal Server Error: {e}"
            raise OBIONEError(message) from e
        else:
            return morphology_metrics
