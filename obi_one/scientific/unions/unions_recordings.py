from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.simulation.recording import (
    SomaVoltageRecording,
    TimeWindowSomaVoltageRecording,
)

RecordingUnion = Annotated[
    SomaVoltageRecording | TimeWindowSomaVoltageRecording, Discriminator("type")
]


class RecordingReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = RecordingUnion
