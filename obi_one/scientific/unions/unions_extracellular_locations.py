from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.blocks.extracellular_locations import XYZExtracellularLocations

ExtracellularLocationsUnion = Annotated[XYZExtracellularLocations, Discriminator("type")]
