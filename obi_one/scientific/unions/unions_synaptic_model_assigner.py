from typing import Annotated, Any, ClassVar, cast

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.synaptic_model_assigners.all_pairs import (
    AllPairsSynapticModelAssigner,
)
from obi_one.scientific.blocks.synaptic_model_assigners.base import SynapseModelAssigner
from obi_one.scientific.blocks.synaptic_model_assigners.inter_neuron_set import (
    InterNeuronSetSynapticModelAssigner,
)
from obi_one.scientific.blocks.synaptic_model_assigners.presyn_neuron_set import (
    PresynapticNeuronSetSynapticModelAssigner,
)

SynapticModelAssignerUnion = Annotated[
    InterNeuronSetSynapticModelAssigner
    | PresynapticNeuronSetSynapticModelAssigner
    | AllPairsSynapticModelAssigner,
    Discriminator("type"),
]


class SynapticModelAssignerReference(BlockReference):
    """A reference to a SynapticModelAssigner block."""

    allowed_block_types: ClassVar[Any] = SynapticModelAssignerUnion

    @property
    def block(self) -> SynapseModelAssigner:
        """Returns the block associated with this reference."""
        return cast("SynapseModelAssigner", super().block)

    @block.setter
    def block(self, value: SynapseModelAssigner) -> None:
        BlockReference.block.fset(self, value)
