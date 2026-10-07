"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.distributions.gamma import (
    ClassVar,
    Distribution,
    Field,
    GammaDistribution,
    np,
    PositiveFloat,
    SchemaKey,
    UIElement,
)

__all__ = [
    "ClassVar",
    "Distribution",
    "Field",
    "GammaDistribution",
    "np",
    "PositiveFloat",
    "SchemaKey",
    "UIElement",
]
