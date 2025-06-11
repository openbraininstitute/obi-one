from obi_one.scientific.simulation.timestamps import (
    RegularTimestamps,
)

TimestampsUnion = RegularTimestamps

from obi_one.core.block_reference import BlockReference
from typing import ClassVar, Any
class TimestampsBlockReference(BlockReference):
    """A reference to a NeuronSet block."""
    
    allowed_block_types: ClassVar[Any] = TimestampsUnion
