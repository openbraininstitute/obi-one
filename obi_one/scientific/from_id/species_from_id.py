from entitysdk.models import Species

from obi_one.core.entity_from_id import IdentifiableFromID


class SpeciesFromID(IdentifiableFromID[Species]):
    @classmethod
    def entitysdk_class(cls) -> type[Species]:
        return Species
