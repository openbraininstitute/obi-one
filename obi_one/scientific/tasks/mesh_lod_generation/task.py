"""Task implementation: generate LOD meshes for a registered EM-cell OBJ asset.

This module is executed remotely by the obi-one launch-system. It:
1. Reads the MeshLodGenerationScanConfig from the TaskConfig entity.
2. Downloads the source OBJ asset from entitycore.
3. Runs ultraliser LOD generation.
4. Uploads the resulting LOD directory block back onto the EMCellMesh entity.
"""

from __future__ import annotations

import pathlib
import tempfile
from typing import TYPE_CHECKING

import ultraliser
from entitysdk.models import EMCellMesh
from entitysdk.types import AssetLabel

from obi_one.core.task import Task

# Guard imports used strictly for type-hinting annotations
if TYPE_CHECKING:
    import os
    from uuid import UUID

    import entitysdk

    from obi_one.scientific.tasks.mesh_lod_generation.config import MeshLodGenerationScanConfig


def _download_obj(
    client: entitysdk.Client,
    entity_id: UUID,
    obj_asset_id: UUID,
    dest_path: pathlib.Path,
) -> None:
    content: bytes = client.download_content(
        entity_id=entity_id,
        entity_type=EMCellMesh,
        asset_id=obj_asset_id,
    )
    dest_path.write_bytes(content)


def _generate_lods(
    obj_path: pathlib.Path,
    output_dir: pathlib.Path,
) -> dict[os.PathLike, os.PathLike]:
    output_dir.mkdir(parents=True, exist_ok=True)

    mesh = ultraliser.Mesh(file_name=str(obj_path), verbose=False)  # ty:ignore[unresolved-attribute]
    generator = ultraliser.LODGenerator(mesh)  # ty:ignore[unresolved-attribute]
    generator.generate_web_lods(str(output_dir))

    # Explicitly type hint the dictionary to use os.PathLike to satisfy invariant checks
    lod_files: dict[os.PathLike, os.PathLike] = {
        pathlib.Path(p.name): p for p in output_dir.iterdir() if p.is_file()
    }

    if not lod_files:
        msg = "ultraliser produced no LOD output files"
        raise RuntimeError(msg)

    return lod_files


def _upload_lod_directory(
    client: entitysdk.Client,
    entity_id: UUID,
    lod_files: dict[os.PathLike, os.PathLike],
) -> str:
    result = client.upload_directory(
        entity_id=entity_id,
        entity_type=EMCellMesh,
        name="lod-mesh-directory",
        paths=lod_files,
        label=AssetLabel.lod_mesh_block,
        metadata=None,
    )
    asset_id = str(result.id) if hasattr(result, "id") else str(result[0].id)
    return asset_id


class MeshLODGenerationTask(Task):
    config: MeshLodGenerationScanConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client,
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,
    ) -> str:
        entity_id = self.config.entity_id
        obj_asset_id = self.config.obj_asset_id

        with tempfile.TemporaryDirectory(prefix="mesh_lod_") as tmp:
            tmp_path = pathlib.Path(tmp)
            obj_path = tmp_path / "input.obj"
            output_dir = tmp_path / "output_lods"

            _download_obj(db_client, entity_id, obj_asset_id, obj_path)
            lod_files = _generate_lods(obj_path, output_dir)
            asset_id = _upload_lod_directory(db_client, entity_id, lod_files)

        execution_activity = MeshLODGenerationTask._get_execution_activity(
            db_client=db_client, execution_activity_id=execution_activity_id
        )
        MeshLODGenerationTask._update_execution_activity(
            db_client=db_client,
            execution_activity=execution_activity,
            generated=[asset_id],
        )
        return asset_id
