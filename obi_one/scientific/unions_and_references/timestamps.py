from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.core.exception import OBIONEError
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
    timestamps_reference: TimestampsReference | None,
) -> TimestampsUnion:
    """Returns the timestamps block a timestamps reference points at."""
    if timestamps_reference is None:
        msg = (
            "Timestamps reference is still unset at resolution time. Every reference field that "
            "may be left unset must declare a SchemaKey.REFERENCE_TAG, and the task must map that "
            "tag to a default in GenerateSimulationTask._fill_none_references."
        )
        raise OBIONEError(msg)

    return timestamps_reference.block  # ty:ignore[invalid-return-type]
