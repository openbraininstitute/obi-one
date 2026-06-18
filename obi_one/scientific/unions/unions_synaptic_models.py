from typing import Annotated, Any, ClassVar, cast

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.synaptic_models.base import SynapticModelBase
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    # CorrelatedExcitatoryTsodyksMarkramSynapticModel,
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
)

SynapticModelUnion = Annotated[
    ExcitatoryTsodyksMarkramSynapticModel
    | InhibitoryTsodyksMarkramSynapticModel,  # | CorrelatedExcitatoryTsodyksMarkramSynapticModel,
    Discriminator("type"),
]


class SynapticModelReference(BlockReference):
    """A reference to a SynapticModel block."""

    allowed_block_types: ClassVar[Any] = SynapticModelUnion

    @property
    def block(self) -> SynapticModelBase:
        """Returns the block associated with this reference."""
        if isinstance(super().block, SynapticModelBase):
            return cast("SynapticModelBase", super().block)
        msg = f"Expected block of type SynapticModelBase, but got {type(super().block)}"
        raise TypeError(msg)

    @block.setter
    def block(self, value: SynapticModelBase) -> None:
        BlockReference.block.fset(self, value)
