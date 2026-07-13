from typing import Annotated, Any, ClassVar, cast

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.distributions.base import Distribution
from obi_one.scientific.blocks.distributions.constant import (
    FloatConstantDistribution,
    IntConstantDistribution,
)
from obi_one.scientific.blocks.distributions.discrete import IntDiscreteDistribution
from obi_one.scientific.blocks.distributions.exponential import ExponentialDistribution
from obi_one.scientific.blocks.distributions.gamma import GammaDistribution
from obi_one.scientific.blocks.distributions.lognormal import LogNormalDistribution
from obi_one.scientific.blocks.distributions.normal import NormalDistribution
from obi_one.scientific.blocks.distributions.poisson import PoissonDistribution
from obi_one.scientific.blocks.distributions.uniform import (
    FloatUniformDistribution,
    IntUniformDistribution,
)

_ALL_FLOAT_DISTRIBUTIONS = (
    FloatConstantDistribution
    | FloatUniformDistribution
    | ExponentialDistribution
    | GammaDistribution
    | NormalDistribution
    | LogNormalDistribution
    | PoissonDistribution
)

_ALL_INT_DISTRIBUTIONS = IntConstantDistribution | IntUniformDistribution | IntDiscreteDistribution

_ALL_DISTRIBUTIONS = _ALL_FLOAT_DISTRIBUTIONS | _ALL_INT_DISTRIBUTIONS

AllDistributionsUnion = Annotated[
    _ALL_DISTRIBUTIONS,
    Discriminator("type"),
]


class AllDistributionsReference(BlockReference):
    """A reference to a Distribution block."""

    allowed_block_types: ClassVar[Any] = AllDistributionsUnion

    @property
    def block(self) -> Distribution:
        """Returns the Distribution block associated with this reference."""
        return cast("Distribution", super().block)

    @block.setter
    def block(self, value: Distribution) -> None:
        BlockReference.block.fset(self, value)
