"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, import-private-name, unsorted-imports]

from obi_one_lazy.scientific.unions_and_references.distributions import (
    _ALL_DISTRIBUTIONS,
    _ALL_FLOAT_DISTRIBUTIONS,
    _ALL_INT_DISTRIBUTIONS,
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
