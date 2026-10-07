"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.core.registry import (
    annotations,
    block_ref_registry,
    BlockReferenceRegistry,
    dataclass,
    task_registry,
    TaskRegistration,
    TaskRegistry,
    TYPE_CHECKING,
)

__all__ = [
    "annotations",
    "block_ref_registry",
    "BlockReferenceRegistry",
    "dataclass",
    "task_registry",
    "TaskRegistration",
    "TaskRegistry",
    "TYPE_CHECKING",
]
