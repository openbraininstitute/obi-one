from typing import ClassVar

import entitysdk
from entitysdk import Client
from entitysdk.models import SkeletonizationExecution
from pydantic import PrivateAttr
from uuid import UUID

from obi_one.core.entity_from_id import EntityFromID
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID


class EMCellMeshFromID(EntityFromID):
    entitysdk_class: ClassVar[type[entitysdk.models.entity.Entity]] = entitysdk.models.EMCellMesh
    _entity: entitysdk.models.EMCellMesh | None = PrivateAttr(default=None)

    def cell_morphology_ids(
        self, db_client: Client | None = None, only_project: bool = False
    ) -> list[UUID]:
        query = db_client.search_entity(
            entity_type=SkeletonizationExecution,
            query= {
                "used__id": self.id_str
            }
        )
        morphology_ids = []
        for activity in query:
            for generated_morph in activity.generated:
                if (not generated_morph.authorized_public) or (not only_project):
                    morphology_ids.append(generated_morph.id)
        return morphology_ids
    
    def cell_morphologies(
        self, db_client: Client | None = None, only_project: bool = False
    ) -> list[CellMorphologyFromID]:
        morph_ids = self.cell_morphology_ids(
            db_client=db_client, only_project=only_project
        )
        morph_from_ids = [
            CellMorphologyFromID(id_str=str(id_)) for id_ in morph_ids
        ]
        return morph_from_ids
