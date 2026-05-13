from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.neuronal_manipulations.neuronal_manipulations import (
    ByNeuronMechanismVariableNeuronalManipulation,
    BySectionListMechanismVariableNeuronalManipulation,
    CircuitByNeuronMechanismVariableNeuronalManipulation,
    CircuitBySectionListMechanismVariableNeuronalManipulation,
)

NeuronalManipulationUnion = Annotated[
    BySectionListMechanismVariableNeuronalManipulation
    | ByNeuronMechanismVariableNeuronalManipulation,
    Discriminator("type"),
]


class NeuronalManipulationReference(BlockReference):
    """A reference to a NeuronalManipulation block."""

    allowed_block_types: ClassVar[Any] = NeuronalManipulationUnion


CircuitNeuronalManipulationUnion = Annotated[
    CircuitBySectionListMechanismVariableNeuronalManipulation
    | CircuitByNeuronMechanismVariableNeuronalManipulation,
    Discriminator("type"),
]


class CircuitNeuronalManipulationReference(BlockReference):
    """A reference to a circuit NeuronalManipulation block."""

    allowed_block_types: ClassVar[Any] = CircuitNeuronalManipulationUnion
