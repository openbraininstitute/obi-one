from obi_one.scientific.simulation.recording import SomaVoltageRecording, TimeWindowSomaVoltageRecording

# RecordingUnion = (SomaVoltageRecording |
#                   TimeWindowSomaVoltageRecording)

from pydantic import Field
from typing import Union, Annotated
RecordingUnion = Annotated[Union[(SomaVoltageRecording,
                  TimeWindowSomaVoltageRecording)], 
                  Field(discriminator='type')]

from obi_one.core.block_reference import BlockReference
from typing import ClassVar, Any
class RecordingReference(BlockReference):
    """A reference to a StimulusUnion block."""
    
    allowed_block_types: ClassVar[Any] = RecordingUnion