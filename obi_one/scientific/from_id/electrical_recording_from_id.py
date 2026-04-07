from typing import ClassVar

import entitysdk
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID


class ElectricalRecordingFromID(EntityFromID):
    entitysdk_class: ClassVar[type[entitysdk.models.entity.Entity]] = entitysdk.models.ElectricalRecording
    _entity: entitysdk.models.ElectricalRecording | None = PrivateAttr(default=None)
