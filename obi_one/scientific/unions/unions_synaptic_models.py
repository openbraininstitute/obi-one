from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    CorrelatedTsodyksMarkramSynapticModel,
    TsodyksMarkramSynapticModel,
)

SynapticModelUnion = Annotated[
    TsodyksMarkramSynapticModel | CorrelatedTsodyksMarkramSynapticModel,
    Discriminator("type"),
]


class SynapticModelReference(BlockReference):
    """A reference to a SynapticModel block."""

    allowed_block_types: ClassVar[Any] = SynapticModelUnion
