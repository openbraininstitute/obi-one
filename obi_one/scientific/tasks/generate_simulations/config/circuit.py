from typing import Annotated

from pydantic import Field

from obi_one.scientific.from_id.circuit_from_id import (
    CircuitFromID,
)
from obi_one.scientific.library.circuit import Circuit

CircuitDiscriminator = Annotated[Circuit | CircuitFromID, Field(discriminator="type")]
