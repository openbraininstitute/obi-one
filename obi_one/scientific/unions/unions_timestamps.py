from obi_one.scientific.simulation.timestamps import (
    SingleTimestamp, 
    RegularTimestamps
)

TimestampsUnion = (
    SingleTimestamp
    | RegularTimestamps
)

from obi_one.core.block_reference import BlockReference
from typing import ClassVar, Any
class TimestampsReference(BlockReference):
    """A reference to a NeuronSet block."""
    
    allowed_block_types: ClassVar[Any] = TimestampsUnion
