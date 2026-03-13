from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.distributions.constant import (
    FloatConstantDistribution,
    IntegerConstantDistribution,
    NegativeConstantDistribution,
    NegativeIntegerConstantDistribution,
    NonNegativeConstantDistribution,
    NonNegativeIntegerConstantDistribution,
    NonPositiveConstantDistribution,
    NonPositiveIntegerConstantDistribution,
    PositiveConstantDistribution,
    PositiveIntegerConstantDistribution,
)

from obi_one.scientific.blocks.distributions.uniform import (
    FloatUniformDistribution,
    IntegerUniformDistribution,
    NonPositiveIntegerUniformDistribution,
    PositiveUniformDistribution,
    NonNegativeUniformDistribution,
    NegativeUniformDistribution,
    NonPositiveUniformDistribution,
    PositiveIntegerUniformDistribution,
    NonNegativeIntegerUniformDistribution,
    NegativeIntegerUniformDistribution,
)

_CONSTANT_DISTRIBUTIONS = (
    FloatConstantDistribution
    | IntegerConstantDistribution
    | PositiveConstantDistribution
    | NonNegativeConstantDistribution
    | NegativeConstantDistribution
    | NonPositiveConstantDistribution
    | PositiveIntegerConstantDistribution
    | NonNegativeIntegerConstantDistribution
    | NegativeIntegerConstantDistribution
    | NonPositiveIntegerConstantDistribution
)

_UNIFORM_DISTRIBUTIONS = (
    FloatUniformDistribution
    | IntegerUniformDistribution
    | PositiveUniformDistribution
    | NonNegativeUniformDistribution
    | NegativeUniformDistribution
    | NonPositiveUniformDistribution
    | PositiveIntegerUniformDistribution
    | NonNegativeIntegerUniformDistribution
    | NegativeIntegerUniformDistribution
    | NonPositiveIntegerUniformDistribution
)

_SYNAPTIC_PARAMETERIZATION_DISTRIBUTIONS = _CONSTANT_DISTRIBUTIONS | _UNIFORM_DISTRIBUTIONS


SynapticParameterizationDistributionsUnion = Annotated[
    _SYNAPTIC_PARAMETERIZATION_DISTRIBUTIONS,
    Discriminator("type"),
]


class SynapticParameterizationDistributionReference(BlockReference):
    """A reference to a SynapticParameterizationDistribution block."""

    allowed_block_types: ClassVar[Any] = SynapticParameterizationDistributionsUnion
