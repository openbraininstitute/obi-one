from obi_one.scientific.simulation.recording import (
    SomaVoltageRecording,
    TimeWindowSomaVoltageRecording,
)

RecordingUnion = SomaVoltageRecording | TimeWindowSomaVoltageRecording

from typing import Any, ClassVar

from obi_one.core.block_reference import BlockReference


class RecordingReference(BlockReference):
    """A reference to a StimulusUnion block."""

    allowed_block_types: ClassVar[Any] = RecordingUnion
