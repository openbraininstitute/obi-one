"""Asset and lifecycle rules of an EM cell mesh whose OBJ is converted to GLB.

The mesh stays ``draft`` while it is converted. It ends ``active`` with only a GLB, or
``disqualified`` with no mesh file: the OBJ is never kept.
"""

import logging
from uuid import UUID

from entitysdk import Client
from entitysdk.models import Asset, EMCellMesh
from entitysdk.types import AssetLabel, AssetStatus, ContentType, EntityLifecycleStatus
from entitysdk.utils.asset import filter_assets

L = logging.getLogger(__name__)


def obj_assets(mesh: EMCellMesh) -> list[Asset]:
    """All OBJ surface mesh assets, whatever their upload status."""
    return filter_assets(
        mesh.assets,
        {"label": AssetLabel.cell_surface_mesh, "content_type": ContentType.application_obj},
    )


def _all_glb_assets(mesh: EMCellMesh) -> list[Asset]:
    return filter_assets(
        mesh.assets,
        {"label": AssetLabel.cell_surface_mesh, "content_type": ContentType.model_gltf_binary},
    )


def glb_assets(mesh: EMCellMesh) -> list[Asset]:
    """The GLB surface mesh assets whose upload completed."""
    return [asset for asset in _all_glb_assets(mesh) if asset.status == AssetStatus.created]


def _delete_assets(db_client: Client, mesh: EMCellMesh, assets: list[Asset]) -> None:
    for asset in assets:
        db_client.delete_asset(entity_id=mesh.id, entity_type=EMCellMesh, asset_id=asset.id)


def delete_obj_assets(db_client: Client, mesh: EMCellMesh) -> None:
    _delete_assets(db_client, mesh, obj_assets(mesh))


def set_lifecycle_status(db_client: Client, mesh_id: UUID, status: EntityLifecycleStatus) -> None:
    db_client.update_entity(
        entity_id=mesh_id,
        entity_type=EMCellMesh,
        attrs_or_entity={"lifecycle_status": status},
    )
    L.info(f"EM cell mesh {mesh_id} is now {status}")


def settle_failed_conversion(db_client: Client, mesh_id: UUID) -> None:
    """Deletes the OBJ and any unfinished GLB, then marks the mesh active if a GLB was uploaded,
    else disqualified.

    The status is set even when a delete fails, so the mesh never stays ``draft``; the delete
    error is raised after it.
    """
    mesh = db_client.get_entity(entity_id=mesh_id, entity_type=EMCellMesh)
    status = (
        EntityLifecycleStatus.active if glb_assets(mesh) else EntityLifecycleStatus.disqualified
    )
    unfinished_glbs = [a for a in _all_glb_assets(mesh) if a.status != AssetStatus.created]
    try:
        _delete_assets(db_client, mesh, [*obj_assets(mesh), *unfinished_glbs])
    finally:
        set_lifecycle_status(db_client, mesh_id, status)
