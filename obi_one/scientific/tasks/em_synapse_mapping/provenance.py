import logging

from entitysdk import Client
from entitysdk.models import (
    EMCellMesh,
    EMDenseReconstructionDataset,
)

from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID

L = logging.getLogger(__name__)


def resolve_provenance(
    db_client: Client, morph_from_id: CellMorphologyFromID
) -> tuple[int, EMCellMesh, EMDenseReconstructionDataset]:
    source_mesh_entity = morph_from_id.source_mesh_entity(db_client=db_client)
    pt_root_id = source_mesh_entity.dense_reconstruction_cell_id
    source_dataset = db_client.get_entity(
        entity_id=source_mesh_entity.em_dense_reconstruction_dataset.id,  # ty:ignore[invalid-argument-type, unresolved-attribute]
        entity_type=EMDenseReconstructionDataset,
    )
    return pt_root_id, source_mesh_entity, source_dataset
