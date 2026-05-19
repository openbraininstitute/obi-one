from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.distributions.constant import (
    FloatConstantDistribution,
    IntConstantDistribution,
)
from obi_one.scientific.blocks.distributions.exponential import ExponentialDistribution
from obi_one.scientific.blocks.distributions.gamma import GammaDistribution
from obi_one.scientific.blocks.distributions.uniform import (
    FloatUniformDistribution,
    IntUniformDistribution,
)

_ALL_FLOAT_DISTRIBUTIONS = (
    FloatConstantDistribution
    | FloatUniformDistribution
    | ExponentialDistribution
    | GammaDistribution
)
_ALL_INT_DISTRIBUTIONS = IntConstantDistribution | IntUniformDistribution

_ALL_DISTRIBUTIONS = _ALL_FLOAT_DISTRIBUTIONS | _ALL_INT_DISTRIBUTIONS

AllDistributionsUnion = Annotated[
    _ALL_DISTRIBUTIONS,
    Discriminator("type"),
]


class AllDistributionsReference(BlockReference):
    """A reference to a Distribution block."""

    allowed_block_types: ClassVar[Any] = AllDistributionsUnion
