from typing import ClassVar

import entitysdk
from entitysdk.models import SimulatableExtracellularRecordingArray
from entitysdk.models.entity import Entity
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID


class SimulatableExtracellularRecordingArrayFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = SimulatableExtracellularRecordingArray
    _entity: SimulatableExtracellularRecordingArray | None = PrivateAttr(default=None)

    def entity(self, db_client: entitysdk.client.Client) -> SimulatableExtracellularRecordingArray:
        super().entity(db_client=db_client)
        return self._entity
