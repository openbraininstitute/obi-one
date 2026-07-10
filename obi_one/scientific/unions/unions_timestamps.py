from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.timestamps.regular import RegularTimestamps
from obi_one.scientific.blocks.timestamps.single import SingleTimestamp

_TIMESTAMPS = SingleTimestamp | RegularTimestamps
TimestampsUnion = Annotated[_TIMESTAMPS, Discriminator("type")]


class TimestampsReference(BlockReference):
    """A reference to a NeuronSet block."""

    allowed_block_types: ClassVar[Any] = TimestampsUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_TIMESTAMPS)
    }


def resolve_timestamps_ref_to_timestamps_block(
    timestamps_reference: TimestampsReference | None, default_timestamps: TimestampsUnion | None
) -> TimestampsUnion:
    if timestamps_reference is None:
        if default_timestamps is None:
            msg = (
                "Either a timestamps block reference must be provided or a default "
                "timestamps block must be set"
            )
            raise ValueError(msg)
        return default_timestamps

    return timestamps_reference.block  # ty:ignore[invalid-return-type]
