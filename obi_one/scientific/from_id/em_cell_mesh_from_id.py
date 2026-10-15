from entitysdk.models import EMCellMesh
from pydantic import Field

from obi_one.core.entity_from_id import EntityFromID


class EMCellMeshFromID(EntityFromID[EMCellMesh]):
    entitysdk_type: type[EMCellMesh] = Field(default=EMCellMesh, exclude=True, repr=False)
