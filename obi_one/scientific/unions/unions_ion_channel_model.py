from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.ion_channel_model import (
    IonChannelModelWithConductance,
    IonChannelModelWithMaxPermeability,
    IonChannelModelWithoutConductance,
)

_ION_CHANNEL_MODELS = (
    IonChannelModelWithConductance
    | IonChannelModelWithMaxPermeability
    | IonChannelModelWithoutConductance
)
IonChannelModelUnion = Annotated[
    _ION_CHANNEL_MODELS,
    Discriminator("type"),
]


class IonChannelModelReference(BlockReference):
    """A reference to an IonChannelModel block."""

    allowed_block_types: ClassVar[Any] = IonChannelModelUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_ION_CHANNEL_MODELS)
    }
