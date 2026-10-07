"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.core.block_reference import (
    abc,
    Annotated,
    Any,
    Block,
    BlockReference,
    ClassVar,
    Discriminator,
    Field,
    get_args,
    OBIBaseModel,
)

__all__ = [
    "abc",
    "Annotated",
    "Any",
    "Block",
    "BlockReference",
    "ClassVar",
    "Discriminator",
    "Field",
    "get_args",
    "OBIBaseModel",
]
