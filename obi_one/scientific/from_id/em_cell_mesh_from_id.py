from typing import ClassVar

from entitysdk.models import EMCellMesh

from obi_one.core.entity_from_id import EntityFromID


class EMCellMeshFromID(EntityFromID[EMCellMesh]):
    entitysdk_class: ClassVar[type[EMCellMesh]] = EMCellMesh
