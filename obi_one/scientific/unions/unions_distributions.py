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


# COMBINED ALL DISTRIBUTIONS
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


# COMPATIBLE COMBINED FLOAT DISTRIBUTIONS
_ALL_NON_NEGATIVE_FLOAT_COMPATIBLE_DISTRIBUTIONS = (
    _ALL_NON_NEGATIVE_FLOAT_DISTRIBUTIONS | _ALL_POSITIVE_FLOAT_DISTRIBUTIONS
)

_ALL_POSITIVE_FLOAT_COMPATIBLE_DISTRIBUTIONS = _ALL_POSITIVE_FLOAT_DISTRIBUTIONS

_ALL_NON_POSITIVE_FLOAT_COMPATIBLE_DISTRIBUTIONS = (
    _ALL_NON_POSITIVE_FLOAT_DISTRIBUTIONS | _ALL_NEGATIVE_FLOAT_DISTRIBUTIONS
)

_ALL_NEGATIVE_FLOAT_COMPATIBLE_DISTRIBUTIONS = _ALL_NEGATIVE_FLOAT_DISTRIBUTIONS

# COMPATIBLE COMBINED INT DISTRIBUTIONS
_ALL_NON_NEGATIVE_INT_COMPATIBLE_DISTRIBUTIONS = (
    _ALL_NON_NEGATIVE_INT_DISTRIBUTIONS | _ALL_POSITIVE_INT_DISTRIBUTIONS
)

_ALL_POSITIVE_INT_COMPATIBLE_DISTRIBUTIONS = _ALL_POSITIVE_INT_DISTRIBUTIONS

_ALL_NON_POSITIVE_INT_COMPATIBLE_DISTRIBUTIONS = (
    _ALL_NON_POSITIVE_INT_DISTRIBUTIONS | _ALL_NEGATIVE_INT_DISTRIBUTIONS
)

_ALL_NEGATIVE_INT_COMPATIBLE_DISTRIBUTIONS = _ALL_NEGATIVE_INT_DISTRIBUTIONS


# DISCRIMINATED ALL UNIONS

AllFloatDistributionsUnion = Annotated[
    _ALL_FLOAT_DISTRIBUTIONS,
    Discriminator("type"),
]

AllIntDistributionsUnion = Annotated[_ALL_INT_DISTRIBUTIONS, Discriminator("type")]

AllDistributionsUnion = Annotated[
    _ALL_DISTRIBUTIONS,
    Discriminator("type"),
]

# DISCRIMINATED COMPATIBLE FLOAT UNIONS

AllNonNegativeFloatCompatibleDistributionsUnion = Annotated[
    _ALL_NON_NEGATIVE_FLOAT_COMPATIBLE_DISTRIBUTIONS,
    Discriminator("type"),
]

AllNegativeFloatCompatibleDistributionsUnion = Annotated[
    _ALL_NEGATIVE_FLOAT_COMPATIBLE_DISTRIBUTIONS,
    Discriminator("type"),
]

AllPositiveFloatCompatibleDistributionsUnion = Annotated[
    _ALL_POSITIVE_FLOAT_COMPATIBLE_DISTRIBUTIONS,
    Discriminator("type"),
]

AllNonPositiveFloatCompatibleDistributionsUnion = Annotated[
    _ALL_NON_POSITIVE_FLOAT_COMPATIBLE_DISTRIBUTIONS,
    Discriminator("type"),
]

# DISCRIMINATED COMPATIBLE INT UNIONS

AllNonNegativeIntCompatibleDistributionsUnion = Annotated[
    _ALL_NON_NEGATIVE_INT_COMPATIBLE_DISTRIBUTIONS,
    Discriminator("type"),
]

AllNegativeIntCompatibleDistributionsUnion = Annotated[
    _ALL_NEGATIVE_INT_COMPATIBLE_DISTRIBUTIONS,
    Discriminator("type"),
]

AllPositiveIntCompatibleDistributionsUnion = Annotated[
    _ALL_POSITIVE_INT_COMPATIBLE_DISTRIBUTIONS,
    Discriminator("type"),
]

AllNonPositiveIntCompatibleDistributionsUnion = Annotated[
    _ALL_NON_POSITIVE_INT_COMPATIBLE_DISTRIBUTIONS,
    Discriminator("type"),
]

# All Block references


class AllDistributionsReference(BlockReference):
    """A reference to a Distribution block."""

    allowed_block_types: ClassVar[Any] = AllDistributionsUnion


class AllFloatDistributionsReference(BlockReference):
    """A reference to a Float Distribution block."""

    allowed_block_types: ClassVar[Any] = AllFloatDistributionsUnion


class AllIntDistributionsReference(BlockReference):
    """A reference to an Int Distribution block."""

    allowed_block_types: ClassVar[Any] = AllIntDistributionsUnion


class AllNonNegativeFloatCompatibleDistributionsReference(BlockReference):
    """A reference to a non-negative float compatible Distribution block."""

    allowed_block_types: ClassVar[Any] = AllNonNegativeFloatCompatibleDistributionsUnion


class AllNegativeFloatCompatibleDistributionsReference(BlockReference):
    """A reference to a negative float compatible Distribution block."""

    allowed_block_types: ClassVar[Any] = AllNegativeFloatCompatibleDistributionsUnion


class AllPositiveFloatCompatibleDistributionsReference(BlockReference):
    """A reference to a positive float compatible Distribution block."""

    allowed_block_types: ClassVar[Any] = AllPositiveFloatCompatibleDistributionsUnion


class AllNonPositiveFloatCompatibleDistributionsReference(BlockReference):
    """A reference to a non-positive float compatible Distribution block."""

    allowed_block_types: ClassVar[Any] = AllNonPositiveFloatCompatibleDistributionsUnion


class AllNonNegativeIntCompatibleDistributionsReference(BlockReference):
    """A reference to a non-negative int compatible Distribution block."""

    allowed_block_types: ClassVar[Any] = AllNonNegativeIntCompatibleDistributionsUnion


class AllNegativeIntCompatibleDistributionsReference(BlockReference):
    """A reference to a negative int compatible Distribution block."""

    allowed_block_types: ClassVar[Any] = AllNegativeIntCompatibleDistributionsUnion


class AllPositiveIntCompatibleDistributionsReference(BlockReference):
    """A reference to a positive int compatible Distribution block."""

    allowed_block_types: ClassVar[Any] = AllPositiveIntCompatibleDistributionsUnion


class AllNonPositiveIntCompatibleDistributionsReference(BlockReference):
    """A reference to a non-positive int compatible Distribution block."""

    allowed_block_types: ClassVar[Any] = AllNonPositiveIntCompatibleDistributionsUnion
