"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.utils.pydantic import (
    order_schema_properties,
    SchemaKey,
)

__all__ = [
    "order_schema_properties",
    "SchemaKey",
]
