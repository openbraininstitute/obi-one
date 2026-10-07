"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.unions_and_references.timestamps import (
    Annotated,
    Any,
    BlockReference,
    ClassVar,
    Discriminator,
    RegularTimestamps,
    resolve_timestamps_ref_to_timestamps_block,
    SingleTimestamp,
    TimestampsReference,
    TimestampsUnion,
)

from obi_one_lazy.scientific.unions_and_references.timestamps import (
    _TIMESTAMPS,
)

__all__ = [
    "Annotated",
    "Any",
    "BlockReference",
    "ClassVar",
    "Discriminator",
    "RegularTimestamps",
    "resolve_timestamps_ref_to_timestamps_block",
    "SingleTimestamp",
    "TimestampsReference",
    "TimestampsUnion",
    "_TIMESTAMPS",
]
