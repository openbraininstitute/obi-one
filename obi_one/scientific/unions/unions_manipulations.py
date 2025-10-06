from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.manipulations import (
    ScaleAcetylcholineUSESynapticManipulation,
    SynapticMgManipulation,
)

SynapticManipulationsUnion = Annotated[
    SynapticMgManipulation | ScaleAcetylcholineUSESynapticManipulation,
    Discriminator("type"),
]


class SynapticManipulationsReference(BlockReference):
    """A reference to a SynapticManipulations block."""

    allowed_block_types: ClassVar[Any] = SynapticManipulationsUnion
