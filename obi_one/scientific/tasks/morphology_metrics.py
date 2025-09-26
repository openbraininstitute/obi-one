import logging
from typing import ClassVar

import entitysdk
from fastapi import HTTPException
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single_config_mixin import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.database.reconstruction_morphology_from_id import ReconstructionMorphologyFromID
from obi_one.scientific.morphology_metrics.morphology_metrics import (
    MorphologyMetricsOutput,
)

L = logging.getLogger(__name__)


class MorphologyMetricsScanConfig(ScanConfig):
    single_coord_class_name: ClassVar[str] = "MorphologyMetricsSingleConfig"
    name: ClassVar[str] = "Morphology Metrics"
    description: ClassVar[str] = "Calculates morphology metrics for a given morphologies."

    class Initialize(Block):
        morphology: ReconstructionMorphologyFromID | list[ReconstructionMorphologyFromID] = Field(
            description="3. Morphology description"
        )

    initialize: Initialize


class MorphologyMetricsSingleConfig(MorphologyMetricsScanConfig, SingleConfigMixin):
    """Calculates morphology metrics for a given morphology."""


class MorphologyMetricsTask(Task):
    config: MorphologyMetricsSingleConfig

    def execute(self, db_client: entitysdk.client.Client = None) -> MorphologyMetricsOutput:
        try:
            L.info("Running Morphology Metrics...")
            morphology_metrics = MorphologyMetricsOutput.from_morphology(
                self.initialize.morphology.neurom_morphology(db_client=db_client)
            )
            L.info(morphology_metrics)

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}") from e
        else:
            return morphology_metrics
