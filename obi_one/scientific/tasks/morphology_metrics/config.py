"""Morphology metrics task configuration."""

from typing import ClassVar

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID


class MorphologyMetricsScanConfig(ScanConfig):
    name: ClassVar[str] = "Morphology Metrics"
    description: ClassVar[str] = "Calculates morphology metrics for a given morphologies."

    class Initialize(Block):
        morphology: CellMorphologyFromID | list[CellMorphologyFromID] = Field(
            description="3. Morphology description"
        )

    initialize: Initialize


class MorphologyMetricsSingleConfig(MorphologyMetricsScanConfig, SingleConfigMixin):
    """Calculates morphology metrics for a given morphology."""
