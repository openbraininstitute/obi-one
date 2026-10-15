from entitysdk.models import Species

from obi_one.core.entity_from_id import DBType, IdentifiableFromID


class SpeciesFromID(IdentifiableFromID[Species]):
    entitysdk_type: DBType[Species] = Species
