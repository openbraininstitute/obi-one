from entitysdk.models import EMCellMesh

from obi_one.core.entity_from_id import EntityFromID


class EMCellMeshFromID(EntityFromID[EMCellMesh]):
    @classmethod
    def entitysdk_class(cls) -> type[EMCellMesh]:
        return EMCellMesh
