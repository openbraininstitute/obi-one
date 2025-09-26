import logging
from typing import ClassVar

import entitysdk
from fastapi import HTTPException
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.single import SingleCoordinateMixin
from obi_one.core.task import Task
from obi_one.database.reconstruction_morphology_from_id import ReconstructionMorphologyFromID
from obi_one.scientific.morphology_metrics.morphology_metrics import (
    MorphologyMetricsOutput,
)

L = logging.getLogger(__name__)


class MorphologyMetricsForm(Form):
    single_coord_class_name: ClassVar[str] = "MorphologyMetrics"
    name: ClassVar[str] = "Morphology Metrics"
    description: ClassVar[str] = "Calculates morphology metrics for a given morphologies."

    class Initialize(Block):
        morphology: ReconstructionMorphologyFromID | list[ReconstructionMorphologyFromID] = Field(
            description="3. Morphology description"
        )

    initialize: Initialize


class MorphologyMetrics(MorphologyMetricsForm, SingleCoordinateMixin):
    """Calculates morphology metrics for a given morphology."""


class MorphologyMetricsTask(Task):
    config: MorphologyMetrics

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
