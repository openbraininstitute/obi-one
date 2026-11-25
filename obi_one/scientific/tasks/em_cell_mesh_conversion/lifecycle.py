"""Asset and lifecycle rules of an EM cell mesh whose OBJ is converted to GLB.

The mesh stays ``draft`` while it is converted. It ends ``active`` with only a GLB, or
``disqualified`` with no mesh file: the OBJ is never kept.
"""

import logging
from uuid import UUID

from entitysdk import Client
from entitysdk.models import Asset, EMCellMesh
from entitysdk.types import AssetLabel, AssetStatus, ContentType, EntityLifecycleStatus

L = logging.getLogger(__name__)


def _surface_mesh_assets(mesh: EMCellMesh, content_type: ContentType) -> list[Asset]:
    return [
        asset
        for asset in mesh.assets or []
        if asset.label == AssetLabel.cell_surface_mesh and asset.content_type == content_type
    ]


def obj_assets(mesh: EMCellMesh) -> list[Asset]:
    """All OBJ surface mesh assets, whatever their upload status."""
    return _surface_mesh_assets(mesh, ContentType.application_obj)


def glb_assets(mesh: EMCellMesh) -> list[Asset]:
    """The GLB surface mesh assets whose upload completed."""
    return [
        asset
        for asset in _surface_mesh_assets(mesh, ContentType.model_gltf_binary)
        if asset.status == AssetStatus.created
    ]


def delete_obj_assets(db_client: Client, mesh: EMCellMesh) -> None:
    for asset in obj_assets(mesh):
        db_client.delete_asset(entity_id=mesh.id, entity_type=EMCellMesh, asset_id=asset.id)


def set_lifecycle_status(db_client: Client, mesh_id: UUID, status: EntityLifecycleStatus) -> None:
    db_client.update_entity(
        entity_id=mesh_id,
        entity_type=EMCellMesh,
        attrs_or_entity={"lifecycle_status": status},
    )
    L.info(f"EM cell mesh {mesh_id} is now {status}")


def settle_failed_conversion(db_client: Client, mesh_id: UUID) -> EntityLifecycleStatus:
    """Deletes the OBJ, then marks the mesh active if a GLB was uploaded, else disqualified.

    Every step is attempted even when an earlier one fails, so that a failure to delete the
    OBJ still leaves the mesh out of ``draft``.
    """
    mesh = db_client.get_entity(entity_id=mesh_id, entity_type=EMCellMesh)
    try:
        delete_obj_assets(db_client, mesh)
    except Exception:  # ruff: ignore[blind-except]
        L.exception(f"Could not delete the OBJ assets of EM cell mesh {mesh_id}")

    status = (
        EntityLifecycleStatus.active if glb_assets(mesh) else EntityLifecycleStatus.disqualified
    )
    set_lifecycle_status(db_client, mesh_id, status)
    return status
