from typing import ClassVar

from entitysdk.models import Species
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import IdentifiableFromID


class SpeciesFromID(IdentifiableFromID):
    entitysdk_class: ClassVar[type[Species]] = Species
    _entity: Species | None = PrivateAttr(default=None)
