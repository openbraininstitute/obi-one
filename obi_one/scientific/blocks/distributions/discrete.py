"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.distributions.discrete import (
    ClassVar,
    Distribution,
    Field,
    IntDiscreteDistribution,
    model_validator,
    np,
    SchemaKey,
    Self,
    UIElement,
)

__all__ = [
    "ClassVar",
    "Distribution",
    "Field",
    "IntDiscreteDistribution",
    "model_validator",
    "np",
    "SchemaKey",
    "Self",
    "UIElement",
]
