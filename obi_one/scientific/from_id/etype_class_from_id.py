from typing import ClassVar

from entitysdk.models import ETypeClass

from obi_one.core.entity_from_id import IdentifiableFromID


class ETypeClassFromID(IdentifiableFromID[ETypeClass]):
    entitysdk_class: ClassVar[type[ETypeClass]] = ETypeClass
