from obi_one.scientific.simulation.manipulations import (
    SynapticMgManipulation, 
    SynapticUseManipulation
)

SynapticManipulationsUnion = (
    SynapticMgManipulation
    | SynapticUseManipulation
)

from obi_one.core.block_reference import BlockReference
from typing import ClassVar, Any
class SynapticManipulationsReference(BlockReference):
    """A reference to a SynapticManipulations block."""

    allowed_block_types: ClassVar[Any] = SynapticManipulationsUnion
