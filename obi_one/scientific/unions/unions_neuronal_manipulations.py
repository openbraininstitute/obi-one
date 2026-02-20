from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.neuronal_manipulations.neuronal_manipulations import (
    ByNeuronMechanismVariableNeuronalManipulation,
    BySectionListMechanismVariableNeuronalManipulation,
)

NeuronalManipulationUnion = Annotated[
    BySectionListMechanismVariableNeuronalManipulation | ByNeuronMechanismVariableNeuronalManipulation,
    Discriminator("type"),
]


class NeuronalManipulationReference(BlockReference):
    """A reference to a NeuronalManipulation block."""

    allowed_block_types: ClassVar[Any] = NeuronalManipulationUnion
