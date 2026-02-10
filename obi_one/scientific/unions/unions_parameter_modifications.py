from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.parameter_modifications.parameter_modifications import (
    BasicParameterModification,
    CustomParameterModification,
)

ParameterModificationUnion = Annotated[
    BasicParameterModification |
    CustomParameterModification,
    Discriminator("type"),
]


class ParameterModificationReference(BlockReference):
    """A reference to a ParameterModification block."""

    allowed_block_types: ClassVar[Any] = ParameterModificationUnion