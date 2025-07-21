from obi_one.scientific.circuit.extracellular_location_sets import XYZExtracellularLocationSet

# ExtracellularLocationSetUnion = XYZExtracellularLocationSet

from pydantic import Field
from typing import Union, Annotated
ExtracellularLocationSetUnion = Annotated[Union[XYZExtracellularLocationSet], Field(discriminator='type')]

