"""Filesystem-input block for the 01_efeature_extraction stage."""

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.from_id.electrical_cell_recording_from_id import (
    ElectricalCellRecordingFromID,
)


class ExtractionInitialize(Block):
    """Filesystem inputs for the extraction stage.

    The extraction stage runs ``bluepyefe.extract.extract_efeatures`` directly on
    the experimental traces — no model metadata, recipes, morphologies, or
    mechanisms are needed here. Those belong to the optimisation stage.
    """

    # Tuple instead of list so the framework doesn't expand it as a scan dimension.
    electrical_cell_recording: tuple[ElectricalCellRecordingFromID, ...] = Field(
        title="Electrical cell recordings",
        description=(
            "ElectricalCellRecording entities to extract features from (>= 1)."
            " Each entity's NWB asset is downloaded into the working directory's"
            " ``ephys_data/`` folder."
        ),
        min_length=1,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER_MULTIPLE,
        },
    )
