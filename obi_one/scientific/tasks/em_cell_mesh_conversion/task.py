import logging
from pathlib import Path
from uuid import UUID

from entitysdk import Client
from entitysdk.models import Asset, EMCellMesh
from entitysdk.types import AssetLabel, ContentType, EntityLifecycleStatus

from obi_one.core.task import Task
from obi_one.db_sdk.em_cell_mesh import (
    delete_obj_assets,
    glb_assets,
    obj_assets,
    set_lifecycle_status,
    settle_failed_conversion,
)
from obi_one.scientific.tasks.em_cell_mesh_conversion.config import (
    EMCellMeshConversionSingleConfig,
)
from obi_one.scientific.tasks.em_cell_mesh_conversion.conversion import (
    OBJ_FILE_NAME,
    MeshConversionError,
    convert_obj_to_glb,
)

L = logging.getLogger(__name__)


class EMCellMeshConversionTask(Task):
    """Replaces the OBJ surface mesh of a draft EM cell mesh with a Draco GLB, then activates it.

    On any failure the OBJ is deleted and the mesh disqualified. A mesh that already has a GLB
    is only cleaned up and activated, so a repeated run does not convert again.
    """

    config: EMCellMeshConversionSingleConfig

    def execute(
        self,
        *,
        db_client: Client,
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,  # ruff: ignore[unused-method-argument]
    ) -> None:
        mesh_id = self.config.em_cell_mesh_id
        try:
            self._convert(db_client=db_client, mesh_id=mesh_id)
        except Exception:
            L.exception(f"Conversion of EM cell mesh {mesh_id} failed")
            settle_failed_conversion(db_client, mesh_id)
            raise

    def _convert(self, *, db_client: Client, mesh_id: UUID) -> None:
        mesh = db_client.get_entity(entity_id=mesh_id, entity_type=EMCellMesh)
        if glb_assets(mesh):
            L.info(f"EM cell mesh {mesh_id} already has a GLB; nothing to convert")
        else:
            work_dir = Path(self.config.coordinate_output_root)
            work_dir.mkdir(parents=True, exist_ok=True)
            obj_asset = self._single_obj_asset(mesh)
            obj_path = self._download_obj(
                db_client=db_client, mesh=mesh, obj_asset=obj_asset, work_dir=work_dir
            )
            glb_path = convert_obj_to_glb(obj_path, work_dir)
            if glb_assets(db_client.get_entity(entity_id=mesh_id, entity_type=EMCellMesh)):
                L.info(f"EM cell mesh {mesh_id} got a GLB while converting; not uploading")
            else:
                L.info(f"Uploading {glb_path.stat().st_size} bytes of GLB")
                db_client.upload_file(
                    entity_id=mesh_id,
                    entity_type=EMCellMesh,
                    file_path=glb_path,
                    file_name=f"{Path(obj_asset.path).stem}.glb",
                    file_content_type=ContentType.model_gltf_binary,
                    asset_label=AssetLabel.cell_surface_mesh,
                )
        delete_obj_assets(db_client, mesh)
        set_lifecycle_status(db_client, mesh_id, EntityLifecycleStatus.active)

    @staticmethod
    def _single_obj_asset(mesh: EMCellMesh) -> Asset:
        assets = obj_assets(mesh)
        if len(assets) != 1:
            msg = f"EM cell mesh {mesh.id} has {len(assets)} OBJ surface meshes instead of one."
            raise MeshConversionError(msg)
        return assets[0]

    @staticmethod
    def _download_obj(
        *, db_client: Client, mesh: EMCellMesh, obj_asset: Asset, work_dir: Path
    ) -> Path:
        L.info(f"Downloading {obj_asset.size} bytes of OBJ")
        return db_client.download_file(
            entity_id=mesh.id,
            entity_type=EMCellMesh,
            asset_id=obj_asset,
            output_path=work_dir / OBJ_FILE_NAME,
        )
