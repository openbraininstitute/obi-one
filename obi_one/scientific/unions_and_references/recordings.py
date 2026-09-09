from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.recordings.ion_channel import IonChannelVariableRecording
from obi_one.scientific.blocks.recordings.morphology_location import (
    MorphologyLocationVoltageRecording,
    TimeWindowMorphologyLocationVoltageRecording,
)
from obi_one.scientific.blocks.recordings.soma import (
    SomaVoltageRecording,
    TimeWindowSomaVoltageRecording,
)

_SOMA_VOLTAGE_RECORDINGS = SomaVoltageRecording | TimeWindowSomaVoltageRecording

_MORPHOLOGY_LOCATION_VOLTAGE_RECORDINGS = (
    MorphologyLocationVoltageRecording | TimeWindowMorphologyLocationVoltageRecording
)

_VOLTAGE_RECORDINGS = _SOMA_VOLTAGE_RECORDINGS | _MORPHOLOGY_LOCATION_VOLTAGE_RECORDINGS

_RECORDINGS = IonChannelVariableRecording | _VOLTAGE_RECORDINGS


RecordingUnion = Annotated[_VOLTAGE_RECORDINGS, Discriminator("type")]

# Morphology-location recordings are excluded: they require a `morphology_locations` block to
# reference, and the ion channel configuration declares no such dictionary. Its circuit is built
# from the selected channel models, so there is no morphology to place a location on either.
IonChannelModelRecordingUnion = Annotated[
    IonChannelVariableRecording | _SOMA_VOLTAGE_RECORDINGS,
    Discriminator("type"),
]

_AllRecordingsUnion = Annotated[_RECORDINGS, Discriminator("type")]


class RecordingReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = _AllRecordingsUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_RECORDINGS)
    }
