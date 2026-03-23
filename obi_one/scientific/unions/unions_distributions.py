from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.distributions.constant import (
    FloatConstantDistribution,
    IntConstantDistribution,
    NegativeFloatConstantDistribution,
    NegativeIntConstantDistribution,
    NonNegativeFloatConstantDistribution,
    NonNegativeIntConstantDistribution,
    NonPositiveFloatConstantDistribution,
    NonPositiveIntConstantDistribution,
    PositiveFloatConstantDistribution,
    PositiveIntConstantDistribution,
)
from obi_one.scientific.blocks.distributions.uniform import (
    FloatUniformDistribution,
    IntUniformDistribution,
    NegativeFloatUniformDistribution,
    NegativeIntUniformDistribution,
    NonNegativeFloatUniformDistribution,
    NonNegativeIntUniformDistribution,
    NonPositiveFloatUniformDistribution,
    NonPositiveIntUniformDistribution,
    PositiveFloatUniformDistribution,
    PositiveIntUniformDistribution,
)

# ATOMIC FLOAT DISTRIBUTIONS
_ALL_UNBOUNDED_FLOAT_DISTRIBUTIONS = FloatConstantDistribution | FloatUniformDistribution

_ALL_NON_NEGATIVE_FLOAT_DISTRIBUTIONS = (
    NonNegativeFloatConstantDistribution | NonNegativeFloatUniformDistribution
)

_ALL_POSITIVE_FLOAT_DISTRIBUTIONS = (
    PositiveFloatConstantDistribution | PositiveFloatUniformDistribution
)

_ALL_NON_POSITIVE_FLOAT_DISTRIBUTIONS = (
    NonPositiveFloatConstantDistribution | NonPositiveFloatUniformDistribution
)

_ALL_NEGATIVE_FLOAT_DISTRIBUTIONS = (
    NegativeFloatConstantDistribution | NegativeFloatUniformDistribution
)

# ATOMIC INT DISTRIBUTIONS
_ALL_UNBOUNDED_INT_DISTRIBUTIONS = IntConstantDistribution | IntUniformDistribution

_ALL_NON_NEGATIVE_INT_DISTRIBUTIONS = (
    NonNegativeIntConstantDistribution | NonNegativeIntUniformDistribution
)

_ALL_POSITIVE_INT_DISTRIBUTIONS = PositiveIntConstantDistribution | PositiveIntUniformDistribution

_ALL_NON_POSITIVE_INT_DISTRIBUTIONS = (
    NonPositiveIntConstantDistribution | NonPositiveIntUniformDistribution
)

_ALL_NEGATIVE_INT_DISTRIBUTIONS = NegativeIntConstantDistribution | NegativeIntUniformDistribution


# COMBINED DISTRIBUTIONS
_ALL_FLOAT_DISTRIBUTIONS = (
    _ALL_UNBOUNDED_FLOAT_DISTRIBUTIONS
    | _ALL_NON_NEGATIVE_FLOAT_DISTRIBUTIONS
    | _ALL_POSITIVE_FLOAT_DISTRIBUTIONS
    | _ALL_NON_POSITIVE_FLOAT_DISTRIBUTIONS
    | _ALL_NEGATIVE_FLOAT_DISTRIBUTIONS
)

_ALL_INT_DISTRIBUTIONS = (
    _ALL_UNBOUNDED_INT_DISTRIBUTIONS
    | _ALL_NON_NEGATIVE_INT_DISTRIBUTIONS
    | _ALL_POSITIVE_INT_DISTRIBUTIONS
    | _ALL_NON_POSITIVE_INT_DISTRIBUTIONS
    | _ALL_NEGATIVE_INT_DISTRIBUTIONS
)

_ALL_DISTRIBUTIONS = _ALL_FLOAT_DISTRIBUTIONS | _ALL_INT_DISTRIBUTIONS


# COMPATIBLE COMBINED DISTRIBUTIONS
_ALL_NON_NEGATIVE_FLOAT_COMPATIBLE_DISTRIBUTIONS = (
    _ALL_NON_NEGATIVE_FLOAT_DISTRIBUTIONS | _ALL_POSITIVE_FLOAT_DISTRIBUTIONS
)

_ALL_POSITIVE_FLOAT_COMPATIBLE_DISTRIBUTIONS = _ALL_POSITIVE_FLOAT_DISTRIBUTIONS

_ALL_NON_POSITIVE_FLOAT_COMPATIBLE_DISTRIBUTIONS = (
    _ALL_NON_POSITIVE_FLOAT_DISTRIBUTIONS | _ALL_NEGATIVE_FLOAT_DISTRIBUTIONS
)

_ALL_NEGATIVE_FLOAT_COMPATIBLE_DISTRIBUTIONS = _ALL_NEGATIVE_FLOAT_DISTRIBUTIONS


AllDistributionsUnion = Annotated[
    _ALL_DISTRIBUTIONS,
    Discriminator("type"),
]


class AllDistributionsReference(BlockReference):
    """A reference to a Distribution block."""

    allowed_block_types: ClassVar[Any] = AllDistributionsUnion
