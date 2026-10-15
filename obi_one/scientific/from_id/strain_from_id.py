from typing import ClassVar

from entitysdk.models import Strain
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import IdentifiableFromID


class StrainFromID(IdentifiableFromID):
    entitysdk_class: ClassVar[type[Strain]] = Strain
    _entity: Strain | None = PrivateAttr(default=None)
