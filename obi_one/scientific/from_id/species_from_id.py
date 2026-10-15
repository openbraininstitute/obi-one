from entitysdk.models import Species

from obi_one.core.entity_from_id import IdentifiableFromID


class SpeciesFromID(IdentifiableFromID[Species]):
    entitysdk_type: type[Species] = Species
