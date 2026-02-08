from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.synaptic_manipulations.connect_disconnect import (
    ConnectSynapticManipulation,
    DisconnectSynapticManipulation,
)
from obi_one.scientific.blocks.synaptic_manipulations.demo import (
    ScaleAcetylcholineUSESynapticManipulation,
    SynapticMgManipulation,
)

_NEW_MANIPULATIONS = DisconnectSynapticManipulation | ConnectSynapticManipulation

SynapticManipulationsUnion = Annotated[
    SynapticMgManipulation | ScaleAcetylcholineUSESynapticManipulation | _NEW_MANIPULATIONS,
    Discriminator("type"),
]


class SynapticManipulationsReference(BlockReference):
    """A reference to a SynapticManipulations block."""

    allowed_block_types: ClassVar[Any] = SynapticManipulationsUnion
