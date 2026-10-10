from typing import ClassVar

from entitysdk.models import SimulatableExtracellularRecordingArray
from entitysdk.models.entity import Entity
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID


class SimulatableExtracellularRecordingArrayFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = SimulatableExtracellularRecordingArray
    _entity: SimulatableExtracellularRecordingArray | None = PrivateAttr(default=None)
