from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.extracellular_locations.extracellular_locations import (
    LinearExtracellularLocations,
    Neuropixels1ExtracellularLocations,
)

_EXTRACELLULAR_LOCATION_BLOCKS = LinearExtracellularLocations | Neuropixels1ExtracellularLocations

ExtracellularLocationsUnion = Annotated[_EXTRACELLULAR_LOCATION_BLOCKS, Discriminator("type")]


class ExtracellularLocationsReference(BlockReference):
    """A reference to an ExtracellularLocationsUnion block."""

    allowed_block_types: ClassVar[Any] = ExtracellularLocationsUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_EXTRACELLULAR_LOCATION_BLOCKS)
    }
