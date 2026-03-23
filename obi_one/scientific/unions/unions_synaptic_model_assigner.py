from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.synaptic_model_assigners.inter_neuron_set import (
    InterNeuronSetSynapticModelAssigner,
)

SynapticModelAssignerUnion = Annotated[
    InterNeuronSetSynapticModelAssigner,
    Discriminator("type"),
]


class SynapticModelAssignerReference(BlockReference):
    """A reference to a SynapticModelAssigner block."""

    allowed_block_types: ClassVar[Any] = SynapticModelAssignerUnion
