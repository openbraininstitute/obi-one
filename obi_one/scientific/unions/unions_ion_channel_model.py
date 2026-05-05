from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.ion_channel_model import (
    IonChannelModelWithConductance,
    IonChannelModelWithMaxPermeability,
    IonChannelModelWithoutConductance,
)

IonChannelModelUnion = Annotated[
    IonChannelModelWithConductance
    | IonChannelModelWithMaxPermeability
    | IonChannelModelWithoutConductance,
    Discriminator("type"),
]


class IonChannelModelReference(BlockReference):
    """A reference to an IonChannelModel block."""

    allowed_block_types: ClassVar[Any] = IonChannelModelUnion
