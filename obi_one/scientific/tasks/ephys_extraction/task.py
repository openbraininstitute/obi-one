"""Electrophysiology metrics task."""

import entitysdk.client

from obi_one.core.exception import OBIONEError
from obi_one.core.task import Task
from obi_one.scientific.library.ephys_extraction import (
    ElectrophysiologyMetricsOutput,
    get_electrophysiology_metrics,
)
from obi_one.scientific.tasks.ephys_extraction.config import ElectrophysiologyMetricsSingleConfig


class ElectrophysiologyMetricsTask(Task):
    """Task to calculate electrophysiological metrics for a given trace."""

    config: ElectrophysiologyMetricsSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client,
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,  # ruff: ignore[unused-method-argument]
    ) -> ElectrophysiologyMetricsOutput:
        try:
            ephys_metrics = get_electrophysiology_metrics(
                trace_id=self.config.initialize.trace_id,
                entity_client=db_client,
                calculated_feature=self.config.initialize.requested_metrics,
                amplitude=self.config.initialize.amplitude,
                stimuli_types=self.config.initialize.protocols,
            )
        except Exception as e:
            message = f"Internal Server Error: {e}"
            raise OBIONEError(message) from e
        else:
            return ephys_metrics
