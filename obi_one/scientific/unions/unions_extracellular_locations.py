from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.blocks.extracellular_locations.extracellular_locations import (
    LinearExtracellularLocations,
    Neuropixels1_0ExtracellularLocations
)

_EXTRACELLULAR_LOCATION_BLOCKS = LinearExtracellularLocations | Neuropixels1_0ExtracellularLocations

ExtracellularLocationsUnion = Annotated[_EXTRACELLULAR_LOCATION_BLOCKS, Discriminator("type")]
