from obi_one.scientific.simulation.manipulations import (
    SynapticMgManipulation, 
    ScaleAcetylcholineUSESynapticManipulation
)

# SynapticManipulationsUnion = (
#     SynapticMgManipulation
#     | ScaleAcetylcholineUSESynapticManipulation
# )

from pydantic import Field, Discriminator
from typing import Union, Annotated
SynapticManipulationsUnion = Annotated[Union[(
    SynapticMgManipulation, 
    ScaleAcetylcholineUSESynapticManipulation
)], Discriminator('type')]


from obi_one.core.block_reference import BlockReference
from typing import ClassVar, Any
class SynapticManipulationsReference(BlockReference):
    """A reference to a SynapticManipulations block."""

    allowed_block_types: ClassVar[Any] = SynapticManipulationsUnion
