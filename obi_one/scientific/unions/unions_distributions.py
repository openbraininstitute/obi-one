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

_CONSTANT_DISTRIBUTIONS = (
    FloatConstantDistribution
    | IntConstantDistribution
    | PositiveFloatConstantDistribution
    | PositiveIntConstantDistribution
    | NegativeFloatConstantDistribution
    | NegativeIntConstantDistribution
    | NonNegativeFloatConstantDistribution
    | NonNegativeIntConstantDistribution
    | NonPositiveFloatConstantDistribution
    | NonPositiveIntConstantDistribution
)

_UNIFORM_DISTRIBUTIONS = (
    FloatUniformDistribution
    | IntUniformDistribution
    | PositiveFloatUniformDistribution
    | PositiveIntUniformDistribution
    | NegativeFloatUniformDistribution
    | NegativeIntUniformDistribution
    | NonNegativeFloatUniformDistribution
    | NonNegativeIntUniformDistribution
    | NonPositiveFloatUniformDistribution
    | NonPositiveIntUniformDistribution
)

_SYNAPTIC_PARAMETERIZATION_DISTRIBUTIONS = _CONSTANT_DISTRIBUTIONS | _UNIFORM_DISTRIBUTIONS


SynapticParameterizationDistributionUnion = Annotated[
    _SYNAPTIC_PARAMETERIZATION_DISTRIBUTIONS,
    Discriminator("type"),
]


class SynapticParameterizationDistributionReference(BlockReference):
    """A reference to a SynapticParameterizationDistribution block."""

    allowed_block_types: ClassVar[Any] = SynapticParameterizationDistributionUnion
