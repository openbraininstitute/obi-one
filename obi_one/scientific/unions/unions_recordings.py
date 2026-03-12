from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.recording import (
    IonChannelVariableRecording,
    SomaVoltageRecording,
    TimeWindowSomaVoltageRecording,
)

_SOMA_VOLTAGE_RECORDINGS = SomaVoltageRecording | TimeWindowSomaVoltageRecording


RecordingUnion = Annotated[_SOMA_VOLTAGE_RECORDINGS, Discriminator("type")]

IonChannelModelRecordingUnion = Annotated[
    _SOMA_VOLTAGE_RECORDINGS | IonChannelVariableRecording,
    Discriminator("type"),
]


class RecordingReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = IonChannelModelRecordingUnion
