"""Task implementation: generate LOD meshes for a registered EM-cell mesh asset.

This module is executed remotely by the obi-one launch-system. It:
1. Reads the MeshLodGenerationSingleConfig from the TaskConfig entity.
2. Downloads the source mesh asset (OBJ or GLB) from entitycore.
3. Runs ultraliser LOD generation.
4. Uploads the resulting LOD directory block back onto the EMCellMesh entity.
"""

from __future__ import annotations

import pathlib
import tempfile
from typing import TYPE_CHECKING, ClassVar

from entitysdk.models import EMCellMesh
from entitysdk.types import AssetLabel

from obi_one.core.task import Task

try:
    import ultraliser

    HAS_MESHING = True
except ImportError:
    HAS_MESHING = False

if TYPE_CHECKING:
    import os
    from uuid import UUID

    import entitysdk

    from obi_one.scientific.tasks.mesh_lod_generation.config import MeshLodGenerationSingleConfig


def _download_mesh(
    client: entitysdk.Client,
    entity_id: UUID,
    mesh_asset_id: UUID,
    dest_path: pathlib.Path,
) -> None:
    content: bytes = client.download_content(
        entity_id=entity_id,
        entity_type=EMCellMesh,
        asset_id=mesh_asset_id,
    )
    dest_path.write_bytes(content)


def _generate_lods(
    mesh_path: pathlib.Path,
    mesh_format: str,
    output_dir: pathlib.Path,
) -> dict[os.PathLike, os.PathLike]:
    output_dir.mkdir(parents=True, exist_ok=True)

    if not HAS_MESHING:
        msg = "ultraliser not installed"
        raise RuntimeError(msg)

    if mesh_format in {"obj", "glb"}:
        mesh = ultraliser.Mesh(file_name=str(mesh_path), verbose=False)  # ty: ignore[unresolved-attribute]
    else:
        msg = f"Unsupported mesh format for LOD generation: {mesh_format}"
        raise RuntimeError(msg)

    generator = ultraliser.LODGenerator(mesh)  # ty: ignore[unresolved-attribute]
    generator.generate_web_lods(str(output_dir))

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
    config: MeshLodGenerationSingleConfig
    client: entitysdk.Client | None = None

    model_config: ClassVar[dict] = {"arbitrary_types_allowed": True}

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client | None = None,
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,
    ) -> str:
        resolved_client = db_client if db_client is not None else self.client
        if resolved_client is None:
            msg = "Client is not provided."
            raise ValueError(msg)
        entity_id = self.config.entity_id
        mesh_asset_id = self.config.mesh_asset_id
        mesh_format = self.config.mesh_format

        with tempfile.TemporaryDirectory(prefix="mesh_lod_") as tmp:
            tmp_path = pathlib.Path(tmp)
            mesh_path = tmp_path / f"input.{mesh_format}"
            output_dir = tmp_path / "output_lods"

            _download_mesh(resolved_client, entity_id, mesh_asset_id, mesh_path)
            lod_files = _generate_lods(mesh_path, mesh_format, output_dir)
            asset_id = _upload_lod_directory(resolved_client, entity_id, lod_files)

        execution_activity = MeshLODGenerationTask._get_execution_activity(
            db_client=resolved_client, execution_activity_id=execution_activity_id
        )
        MeshLODGenerationTask._update_execution_activity(
            db_client=resolved_client,
            execution_activity=execution_activity,
            generated=[asset_id],
        )
        return asset_id
