from obi_one.scientific.simulation.recording import SomaVoltageRecording, TimeWindowSomaVoltageRecording

RecordingUnion = (SomaVoltageRecording |
                  TimeWindowSomaVoltageRecording)

from obi_one.core.block_reference import BlockReference
from typing import ClassVar, Any
class RecordingReference(BlockReference):
    """A reference to a StimulusUnion block."""
    
    allowed_block_types: ClassVar[Any] = RecordingUnion