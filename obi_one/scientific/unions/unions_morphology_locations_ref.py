from typing import Any, ClassVar

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.unions.unions_morphology_locations import MorphologyLocationUnion


class MorphologyLocationsReference(BlockReference):
    """Reference to a block that generates morphology locations."""

    allowed_block_types: ClassVar[Any] = MorphologyLocationUnion
