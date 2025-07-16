from obi_one.scientific.simulation.manipulations import (
    ScaleAcetylcholineUSESynapticManipulation,
    SynapticMgManipulation,
)

SynapticManipulationsUnion = SynapticMgManipulation | ScaleAcetylcholineUSESynapticManipulation

from typing import Any, ClassVar

from obi_one.core.block_reference import BlockReference


class SynapticManipulationsReference(BlockReference):
    """A reference to a SynapticManipulations block."""

    allowed_block_types: ClassVar[Any] = SynapticManipulationsUnion
