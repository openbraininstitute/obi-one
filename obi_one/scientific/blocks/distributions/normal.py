"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.distributions.normal import (
    ClassVar,
    Distribution,
    Field,
    NormalDistribution,
    np,
    PositiveFloat,
    SchemaKey,
    UIElement,
)

__all__ = [
    "ClassVar",
    "Distribution",
    "Field",
    "NormalDistribution",
    "np",
    "PositiveFloat",
    "SchemaKey",
    "UIElement",
]
