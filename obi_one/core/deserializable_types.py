"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.core.deserializable_types import (
    import_module,
    load_class,
    TYPE_MAP,
)

__all__ = [
    "import_module",
    "load_class",
    "TYPE_MAP",
]
