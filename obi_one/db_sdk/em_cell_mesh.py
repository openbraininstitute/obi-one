"""Asset and lifecycle rules of an EM cell mesh whose OBJ is converted to GLB.

The mesh stays ``draft`` while it is converted. It ends ``active`` with only a GLB, or
``disqualified`` with no mesh file: the OBJ is never kept. A mesh that is not ``draft`` is
never changed.
"""

import logging
import tempfile
from pathlib import Path
from uuid import UUID

from entitysdk import Client
from entitysdk.models import Asset, EMCellMesh, TaskActivity, TaskConfig
from entitysdk.types import (
    ActivityStatus,
    AssetLabel,
    AssetStatus,
    ContentType,
    EntityLifecycleStatus,
    TaskActivityType,
    TaskConfigType,
)
from entitysdk.utils.asset import filter_assets

from obi_one.core.serialization_constants import COORDINATE_CONFIG_FILENAME
from obi_one.db_sdk import db_sdk
from obi_one.scientific.tasks.em_cell_mesh_conversion.config import (
    EMCellMeshConversionSingleConfig,
)

L = logging.getLogger(__name__)

UNFINISHED_ACTIVITY_STATUSES = {
    ActivityStatus.created,
    ActivityStatus.pending,
    ActivityStatus.running,
}


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


def _unfinished_glb_assets(mesh: EMCellMesh) -> list[Asset]:
    return [asset for asset in _all_glb_assets(mesh) if asset.status != AssetStatus.created]


def _delete_assets(db_client: Client, mesh: EMCellMesh, assets: list[Asset]) -> None:
    for asset in assets:
        db_client.delete_asset(entity_id=mesh.id, entity_type=EMCellMesh, asset_id=asset.id)


def delete_obj_assets(db_client: Client, mesh: EMCellMesh) -> None:
    _delete_assets(db_client, mesh, obj_assets(mesh))


def delete_unfinished_glb_assets(db_client: Client, mesh: EMCellMesh) -> None:
    _delete_assets(db_client, mesh, _unfinished_glb_assets(mesh))


def set_lifecycle_status(db_client: Client, mesh_id: UUID, status: EntityLifecycleStatus) -> None:
    db_client.update_entity(
        entity_id=mesh_id,
        entity_type=EMCellMesh,
        attrs_or_entity={"lifecycle_status": status},
    )
    L.info(f"EM cell mesh {mesh_id} is now {status}")


def has_unfinished_conversion(db_client: Client, mesh_id: UUID) -> bool:
    """Whether a conversion activity that uses the mesh is still created, pending or running."""
    conversions = db_client.search_entity(
        entity_type=TaskActivity,
        query={
            "used__id": str(mesh_id),
            "task_activity_type": TaskActivityType.em_cell_mesh_conversion__execution,
        },
    )
    return any(activity.status in UNFINISHED_ACTIVITY_STATUSES for activity in conversions)


def register_conversion_config(db_client: Client, mesh: EMCellMesh) -> TaskConfig:
    config = EMCellMeshConversionSingleConfig(em_cell_mesh_id=mesh.id)
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_path = Path(tmp_dir) / COORDINATE_CONFIG_FILENAME
        config_path.write_text(config.model_dump_json())
        task_config, _ = db_sdk.register_task_config_with_asset(
            client=db_client,
            name=f"EM cell mesh conversion {mesh.name}",
            description=f"OBJ to GLB conversion of EM cell mesh {mesh.id}",
            task_config_type=TaskConfigType.em_cell_mesh_conversion__config,
            multiple_value_parameters_dictionary={},
            input_entities=[mesh],  # ty:ignore[invalid-argument-type]
            task_config_file_path=config_path,
        )
    return task_config


def download_obj(db_client: Client, mesh: EMCellMesh, obj_asset: Asset, output_path: Path) -> Path:
    L.info(f"Downloading {obj_asset.size} bytes of OBJ")
    return db_client.download_file(
        entity_id=mesh.id,
        entity_type=EMCellMesh,
        asset_id=obj_asset,
        output_path=output_path,
    )


def settle_failed_conversion(db_client: Client, mesh_id: UUID) -> None:
    """Deletes the OBJ and any unfinished GLB, then marks the mesh active if a GLB was uploaded,
    else disqualified. A mesh that is not draft is left as it is.

    The status is set even when a delete fails, so the mesh never stays ``draft``; the delete
    error is raised after it.
    """
    mesh = db_client.get_entity(entity_id=mesh_id, entity_type=EMCellMesh)
    if mesh.lifecycle_status != EntityLifecycleStatus.draft:
        L.warning(f"EM cell mesh {mesh_id} is {mesh.lifecycle_status}; not settling it")
        return
    status = (
        EntityLifecycleStatus.active if glb_assets(mesh) else EntityLifecycleStatus.disqualified
    )
    try:
        _delete_assets(db_client, mesh, [*obj_assets(mesh), *_unfinished_glb_assets(mesh)])
    finally:
        set_lifecycle_status(db_client, mesh_id, status)
