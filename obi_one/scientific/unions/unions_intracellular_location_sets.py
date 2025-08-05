from obi_one.scientific.circuit.intracellular_location_sets import SectionIntracellularLocationSet

# IntracellularLocationSetUnion = SectionIntracellularLocationSet

from pydantic import Field, Discriminator
from typing import Union, Annotated
IntracellularLocationSetUnion = Annotated[Union[SectionIntracellularLocationSet], Discriminator('type')]
