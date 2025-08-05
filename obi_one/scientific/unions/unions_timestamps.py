from obi_one.scientific.simulation.timestamps import (
    SingleTimestamp, 
    RegularTimestamps
)

from pydantic import Field, Discriminator
from typing import Union, Annotated
TimestampsUnion = Annotated[Union[(
    SingleTimestamp,
    RegularTimestamps
)], Discriminator('type')]

from obi_one.core.block_reference import BlockReference
from typing import ClassVar, Any
class TimestampsReference(BlockReference):
    """A reference to a NeuronSet block."""
    
    allowed_block_types: ClassVar[Any] = TimestampsUnion
