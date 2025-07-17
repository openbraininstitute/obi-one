from typing import Any, ClassVar

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.simulation.timestamps import RegularTimestamps, SingleTimestamp

TimestampsUnion = SingleTimestamp | RegularTimestamps


class TimestampsReference(BlockReference):
    """A reference to a NeuronSet block."""

    allowed_block_types: ClassVar[Any] = TimestampsUnion
