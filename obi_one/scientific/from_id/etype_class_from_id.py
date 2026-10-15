from entitysdk.models import ETypeClass

from obi_one.core.entity_from_id import DBType, IdentifiableFromID


class ETypeClassFromID(IdentifiableFromID[ETypeClass]):
    entitysdk_type: DBType[ETypeClass] = ETypeClass
