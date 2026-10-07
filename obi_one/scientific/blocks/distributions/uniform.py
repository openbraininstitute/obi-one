"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.distributions.uniform import (
    ClassVar,
    Distribution,
    Field,
    FloatUniformDistribution,
    IntUniformDistribution,
    np,
    SchemaKey,
    UIElement,
)

__all__ = [
    "ClassVar",
    "Distribution",
    "Field",
    "FloatUniformDistribution",
    "IntUniformDistribution",
    "np",
    "SchemaKey",
    "UIElement",
]
