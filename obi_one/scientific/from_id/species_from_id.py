from entitysdk.models import Species
from pydantic import Field

from obi_one.core.entity_from_id import IdentifiableFromID


class SpeciesFromID(IdentifiableFromID[Species]):
    entitysdk_type: type[Species] = Field(default=Species, exclude=True, repr=False)
