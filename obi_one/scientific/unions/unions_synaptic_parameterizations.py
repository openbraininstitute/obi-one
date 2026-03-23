from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.synaptic_parameterization.tsodyks_markram import (
    CorrelatedTsodyksMarkramSynapseParameterization,
    TsodyksMarkramSynapseParameterization,
)

SynapticParameterizationUnion = Annotated[
    TsodyksMarkramSynapseParameterization | CorrelatedTsodyksMarkramSynapseParameterization,
    Discriminator("type"),
]


class SynapticParameterizationReference(BlockReference):
    """A reference to a SynapticParameterization block."""

    allowed_block_types: ClassVar[Any] = SynapticParameterizationUnion
