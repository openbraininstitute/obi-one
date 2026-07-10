"""Blocks for the 01_efeature_extraction stage.

The extraction stage runs ``bluepyefe.extract.extract_efeatures`` directly on
the experimental traces, so the only required input is one or more
:class:`~obi_one.scientific.from_id.electrical_cell_recording_from_id.ElectricalCellRecordingFromID`
entities — model assets (recipes, morphologies, mechanisms, params) all belong
to the optimisation stage. The remaining blocks expose the bluepyefe parameters
that influence experimental e-feature extraction.
"""

from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.blocks.initialize import (
    ExtractionInitialize,
)
from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.blocks.protocol_and_feature_selection import (  # noqa: E501
    ProtocolAndFeatureSelection,
)
from obi_one.scientific.tasks.emodel_optimization._01_efeature_extraction.blocks.settings import (
    Settings,
)

__all__ = [
    "ExtractionInitialize",
    "ProtocolAndFeatureSelection",
    "Settings",
]
