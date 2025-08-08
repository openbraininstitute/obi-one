from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.circuit.extracellular_location_sets import XYZExtracellularLocationSet

ExtracellularLocationSetUnion = Annotated[XYZExtracellularLocationSet, Discriminator("type")]
