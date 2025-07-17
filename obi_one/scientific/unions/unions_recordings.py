from typing import Any, ClassVar

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.simulation.recording import (
    SomaVoltageRecording,
    TimeWindowSomaVoltageRecording,
)

RecordingUnion = SomaVoltageRecording | TimeWindowSomaVoltageRecording


class RecordingReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = RecordingUnion
