"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.unions_and_references.distributions import (
    AllDistributionsReference,
    AllDistributionsUnion,
    Annotated,
    Any,
    BlockReference,
    cast,
    ClassVar,
    Discriminator,
    Distribution,
    ExponentialDistribution,
    FloatConstantDistribution,
    FloatUniformDistribution,
    GammaDistribution,
    IntConstantDistribution,
    IntDiscreteDistribution,
    IntUniformDistribution,
    LogNormalDistribution,
    NormalDistribution,
    PoissonDistribution,
)

from obi_one_lazy.scientific.unions_and_references.distributions import (
    _ALL_DISTRIBUTIONS,
    _ALL_FLOAT_DISTRIBUTIONS,
    _ALL_INT_DISTRIBUTIONS,
)

__all__ = [
    "AllDistributionsReference",
    "AllDistributionsUnion",
    "Annotated",
    "Any",
    "BlockReference",
    "cast",
    "ClassVar",
    "Discriminator",
    "Distribution",
    "ExponentialDistribution",
    "FloatConstantDistribution",
    "FloatUniformDistribution",
    "GammaDistribution",
    "IntConstantDistribution",
    "IntDiscreteDistribution",
    "IntUniformDistribution",
    "LogNormalDistribution",
    "NormalDistribution",
    "PoissonDistribution",
    "_ALL_DISTRIBUTIONS",
    "_ALL_FLOAT_DISTRIBUTIONS",
    "_ALL_INT_DISTRIBUTIONS",
]
