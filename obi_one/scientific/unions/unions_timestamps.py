from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.timestamps import RegularTimestamps, SingleTimestamp

TimestampsUnion = Annotated[SingleTimestamp | RegularTimestamps, Discriminator("type")]


class TimestampsReference(BlockReference):
    """A reference to a NeuronSet block."""

    allowed_block_types: ClassVar[Any] = TimestampsUnion


def resolve_timestamps_ref_to_timestamps_block(
    timestamps_reference: TimestampsReference | None, default_timestamps: str
) -> str:
    if timestamps_reference is None:
        return default_timestamps

    return timestamps_reference.block
