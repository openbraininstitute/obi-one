from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.synaptic_manipulations.connect_disconnect import (
    ConnectSynapticManipulation,
    DisconnectSynapticManipulation,
    ScaleWeightSynapticManipulation,
)
from obi_one.scientific.blocks.synaptic_manipulations.deprecated import (
    ScaleAcetylcholineUSESynapticManipulation,
)

_SYNAPTIC_MANIPULATIONS = (
    DisconnectSynapticManipulation
    | ConnectSynapticManipulation
    | ScaleWeightSynapticManipulation
    | ScaleAcetylcholineUSESynapticManipulation
)

SynapticManipulationsUnion = Annotated[
    _SYNAPTIC_MANIPULATIONS,
    Discriminator("type"),
]


class SynapticManipulationsReference(BlockReference):
    """A reference to a SynapticManipulations block."""

    allowed_block_types: ClassVar[Any] = SynapticManipulationsUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_SYNAPTIC_MANIPULATIONS)
    }
