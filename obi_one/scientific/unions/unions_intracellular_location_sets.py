from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.circuit.intracellular_location_sets import SectionIntracellularLocationSet

IntracellularLocationSetUnion = Annotated[SectionIntracellularLocationSet, Discriminator("type")]
