from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.timestamps import RegularTimestamps, SingleTimestamp

TimestampsUnion = Annotated[SingleTimestamp | RegularTimestamps, Discriminator("type")]


class TimestampsReference(BlockReference):
    """A reference to a NeuronSet block."""

    allowed_block_types: ClassVar[Any] = TimestampsUnion
