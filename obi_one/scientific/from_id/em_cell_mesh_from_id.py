from entitysdk.models import EMCellMesh

from obi_one.core.entity_from_id import DBType, EntityFromID


class EMCellMeshFromID(EntityFromID[EMCellMesh]):
    entitysdk_type: DBType[EMCellMesh] = EMCellMesh
