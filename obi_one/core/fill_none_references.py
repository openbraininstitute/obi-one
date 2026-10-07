"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.core.fill_none_references import (
    Block,
    BlockDefault,
    BlockReference,
    Callable,
    fill_none_references_in_config,
    Iterator,
    L,
    logging,
    Mapping,
    NamedTuple,
    resolve_block_default,
    SchemaKey,
)

from obi_one_lazy.core.fill_none_references import (
    _blocks_of,
    _tagged_reference_fields,
)

__all__ = [
    "Block",
    "BlockDefault",
    "BlockReference",
    "Callable",
    "fill_none_references_in_config",
    "Iterator",
    "L",
    "logging",
    "Mapping",
    "NamedTuple",
    "resolve_block_default",
    "SchemaKey",
    "_blocks_of",
    "_tagged_reference_fields",
]
