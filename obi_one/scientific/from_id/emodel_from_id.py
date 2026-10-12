from typing import ClassVar

from entitysdk.models import EModel
from entitysdk.models.entity import Entity
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID


class EModelFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = EModel
    _entity: EModel | None = PrivateAttr(default=None)
