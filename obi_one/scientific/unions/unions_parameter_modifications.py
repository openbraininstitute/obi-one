from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.parameter_modifications.parameter_modifications import (
    AdvancedParameterModification,
    BasicParameterModification
)

ParameterModificationUnion = Annotated[
    BasicParameterModification |
    AdvancedParameterModification,
    Discriminator("type"),
]


class ParameterModificationReference(BlockReference):
    """A reference to a ParameterModification block."""

    allowed_block_types: ClassVar[Any] = ParameterModificationUnion