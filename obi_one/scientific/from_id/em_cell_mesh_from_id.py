from typing import ClassVar

import entitysdk
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID


class EMCellMeshFromID(EntityFromID):
    entitysdk_class: ClassVar[type[entitysdk.models.entity.Entity]] = entitysdk.models.EMCellMesh
    _entity: entitysdk.models.EMCellMesh | None = PrivateAttr(default=None)
