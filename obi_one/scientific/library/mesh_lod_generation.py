"""Library functions for generating and uploading LOD meshes for a registered EM-cell mesh.

The actual ultraliser call runs in an isolated subprocess (not a thread) via
ProcessPoolExecutor.
"""

import asyncio
import logging
import multiprocessing
import os
import pathlib
import tempfile
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from uuid import UUID

import entitysdk.client
from entitysdk.models import EMCellMesh
from entitysdk.types import AssetLabel

from obi_one.scientific.library.morphology_mesh import HAS_MESHING

L = logging.getLogger(__name__)


LOD_GENERATION_TIMEOUT_S = 600


def _generate_lods_worker(mesh_path: str, output_dir: str) -> None:
    """Runs in a separate OS process. Must stay import-safe and picklable (module-level)."""
    import ultraliser as _ultraliser  # noqa: PLC0415  # re-imported fresh in the child process

    L.info(f"[lod-gen] (subprocess) constructing Mesh from {mesh_path}")
    mesh = _ultraliser.Mesh(file_name=mesh_path, verbose=False)  # ty: ignore[unresolved-attribute]
    L.info("[lod-gen] (subprocess) Mesh constructed")

    generator = _ultraliser.LODGenerator(mesh)  # ty: ignore[unresolved-attribute]
    L.info("[lod-gen] (subprocess) LODGenerator constructed, calling generate_web_lods")

    generator.generate_web_lods(output_dir)
    L.info("[lod-gen] (subprocess) generate_web_lods returned")


def _collect_lod_files(output_dir: pathlib.Path) -> dict[os.PathLike, os.PathLike]:
    return {pathlib.Path(p.name): p for p in output_dir.rglob("*") if p.is_file()}


async def _generate_lods(
    mesh_path: pathlib.Path,
    mesh_format: str,
    output_dir: pathlib.Path,
) -> dict[os.PathLike, os.PathLike]:
    await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)

    if not HAS_MESHING:
        msg = "ultraliser not installed"
        raise RuntimeError(msg)

    if mesh_format not in {"obj", "glb"}:
        msg = f"Unsupported mesh format for LOD generation: {mesh_format}"
        raise RuntimeError(msg)

    mp_context = multiprocessing.get_context("spawn")
    loop = asyncio.get_running_loop()
    executor = ProcessPoolExecutor(max_workers=1, mp_context=mp_context)
    try:
        future = executor.submit(_generate_lods_worker, str(mesh_path), str(output_dir))
        try:
            await asyncio.wait_for(
                asyncio.wrap_future(future, loop=loop), timeout=LOD_GENERATION_TIMEOUT_S
            )
        except BrokenProcessPool as exc:
            msg = f"ultraliser crashed while generating LODs (subprocess died): {exc}"
            raise RuntimeError(msg) from exc
        except TimeoutError as exc:
            future.cancel()
            msg = f"LOD generation timed out after {LOD_GENERATION_TIMEOUT_S}s"
            raise RuntimeError(msg) from exc
    finally:
        await loop.run_in_executor(None, executor.shutdown)

    lod_files = await asyncio.to_thread(_collect_lod_files, output_dir)

    if not lod_files:
        msg = "ultraliser produced no LOD output files"
        raise RuntimeError(msg)

    return lod_files


def _delete_existing_asset_by_path(
    client: entitysdk.client.Client,
    entity_id: UUID,
    asset_path: str,
) -> None:
    """Delete an existing asset on this entity whose path exactly matches asset_path, if any."""
    entity = client.get_entity(entity_id=entity_id, entity_type=EMCellMesh)
    existing = next((a for a in entity.assets if a.path == asset_path), None)
    if existing is not None and existing.id is not None:
        L.info("Replacing existing '%s' asset on entity %s", asset_path, entity_id)
        client.delete_asset(entity_id=entity_id, entity_type=EMCellMesh, asset_id=existing.id)


def _upload_lod_directory(
    client: entitysdk.client.Client,
    entity_id: UUID,
    lod_files: dict[os.PathLike, os.PathLike],
) -> str:
    _delete_existing_asset_by_path(client, entity_id, "lod-mesh-directory")
    client.upload_directory(
        entity_id=entity_id,
        entity_type=EMCellMesh,
        name="lod-mesh-directory",
        paths=lod_files,
        label=AssetLabel.lod_mesh_block,
        metadata=None,
    )
    return str(entity_id)


async def try_generate_and_upload_lods(
    client: entitysdk.client.Client,
    entity_id: UUID,
    mesh_path: pathlib.Path,
    mesh_format: str,
) -> str | None:
    """Generate LOD meshes from a local mesh file and upload them."""
    if not HAS_MESHING:
        L.debug("Meshing dependencies not available, skipping LOD generation")
        return None

    try:
        with tempfile.TemporaryDirectory(prefix="mesh_lod_") as tmp:
            output_dir = pathlib.Path(tmp) / "output_lods"
            lod_files = await _generate_lods(mesh_path, mesh_format, output_dir)
            return await asyncio.to_thread(_upload_lod_directory, client, entity_id, lod_files)
    except Exception:  # noqa: BLE001
        L.warning("LOD mesh generation failed for entity %s", entity_id, exc_info=True)
        return None
