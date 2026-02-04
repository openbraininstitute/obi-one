from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.simulation_manipulations.manipulations import (
    ConnectSynapticManipulation,
    DisconnectSynapticManipulation,
    SetSpontaneousMinisRate0HzSynapticManipulation,
    SetSpontaneousMinisRateSynapticManipulation,
)
from obi_one.scientific.blocks.simulation_manipulations.old_manipulations import (
    ScaleAcetylcholineUSESynapticManipulation,
    SynapticMgManipulation,
)

_NEW_MANIPULATIONS = (
    DisconnectSynapticManipulation
    | ConnectSynapticManipulation
    | SetSpontaneousMinisRate0HzSynapticManipulation
    | SetSpontaneousMinisRateSynapticManipulation
)

SynapticManipulationsUnion = Annotated[
    SynapticMgManipulation | ScaleAcetylcholineUSESynapticManipulation | _NEW_MANIPULATIONS,
    Discriminator("type"),
]


class SynapticManipulationsReference(BlockReference):
    """A reference to a SynapticManipulations block."""

    allowed_block_types: ClassVar[Any] = SynapticManipulationsUnion
