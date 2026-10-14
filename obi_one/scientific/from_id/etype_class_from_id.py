from entitysdk.models import ETypeClass

from obi_one.core.entity_from_id import IdentifiableFromID


class ETypeClassFromID(IdentifiableFromID[ETypeClass]):
    @classmethod
    def entitysdk_class(cls) -> type[ETypeClass]:
        return ETypeClass
