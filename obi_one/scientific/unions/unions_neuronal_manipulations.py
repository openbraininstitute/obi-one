from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.neuronal_manipulations.neuronal_manipulations import (
    ByNeuronMechanismVariableNeuronalManipulation,
    BySectionListMechanismVariableNeuronalManipulation,
)

_NEURONAL_MANIPULATIONS = (
    BySectionListMechanismVariableNeuronalManipulation
    | ByNeuronMechanismVariableNeuronalManipulation
)
NeuronalManipulationUnion = Annotated[
    _NEURONAL_MANIPULATIONS,
    Discriminator("type"),
]


class NeuronalManipulationReference(BlockReference):
    """A reference to a NeuronalManipulation block."""

    allowed_block_types: ClassVar[Any] = NeuronalManipulationUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_NEURONAL_MANIPULATIONS)
    }
