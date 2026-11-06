from entitysdk.models import ETypeClass

from obi_one.core.entity_from_id import IdentifiableFromID


class ETypeClassFromID(IdentifiableFromID[ETypeClass]):
    _entitysdk_type: type[ETypeClass] = ETypeClass
