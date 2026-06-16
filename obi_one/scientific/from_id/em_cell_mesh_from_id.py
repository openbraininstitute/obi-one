from typing import ClassVar

import entitysdk
from entitysdk import Client
from entitysdk.models import EMDenseReconstructionDataset
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import EntityFromID


class EMCellMeshFromID(EntityFromID):
    entitysdk_class: ClassVar[type[entitysdk.models.entity.Entity]] = entitysdk.models.EMCellMesh  # ty:ignore[possibly-missing-submodule]
    _entity: entitysdk.models.EMCellMesh | None = PrivateAttr(default=None)  # ty:ignore[possibly-missing-submodule]
    _source_dataset: EMDenseReconstructionDataset | None = PrivateAttr(default=None)

    def pt_root_id(self, db_client: Client) -> int:
        """The dense reconstruction cell identifier (CAVE pt_root_id) of the mesh."""
        return self.entity(db_client=db_client).dense_reconstruction_cell_id  # ty:ignore[unresolved-attribute]

    def cave_version(self, db_client: Client) -> int:
        """The CAVE materialization version (the mesh release version)."""
        return self.entity(db_client=db_client).release_version  # ty:ignore[unresolved-attribute]

    def source_dataset(self, db_client: Client) -> EMDenseReconstructionDataset:
        """The EM dense reconstruction dataset the mesh originates from."""
        if self._source_dataset is None:
            self._source_dataset = db_client.get_entity(
                entity_id=self.entity(db_client=db_client).em_dense_reconstruction_dataset.id,  # ty:ignore[invalid-argument-type, unresolved-attribute]
                entity_type=EMDenseReconstructionDataset,
            )
        return self._source_dataset
