"""Endpoint: register an EM-cell OBJ mesh and its LOD variants.

Pipeline
--------
1. Validate the uploaded .obj file (reuses validate_mesh_reader from mesh_validation).
2. Upload the raw OBJ as an asset attached to the existing EMCellMesh entity
   (same label / content-type that createAssetsAsync used on the frontend).
3. Generate LOD meshes with ``ultraliser.LODGenerator`` (as in lod_generate.ipynb).
4. Upload the entire LOD directory with ``client.upload_directory``.
5. Return a structured response with all asset IDs.
"""

import os
import pathlib
import tempfile
import traceback
from contextlib import ExitStack
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

import entitysdk
import ultraliser
from entitysdk.exception import EntitySDKError
from entitysdk.models import EMCellMesh
from entitysdk.types import AssetLabel, ContentType
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.endpoints.mesh_validation import (
    MAX_FILE_SIZE,
    FileTooLargeError,
    _cleanup_temp_file,
    _handle_file_too_large,
    _save_upload_to_tempfile,
    validate_mesh_reader,
)
from app.errors import ApiErrorCode
from app.logger import L

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/declared",
    tags=["declared"],
    dependencies=[Depends(user_verified)],
)

# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class MeshRegistrationResponse(BaseModel):
    """Schema returned after a successful mesh registration."""

    entity_id: str
    """The EMCellMesh entity the assets were attached to."""

    obj_asset_id: str
    """Asset ID of the original OBJ that was registered."""

    lod_directory_asset_id: str
    """Asset ID of the LOD directory block (contains all LOD OBJ files)."""

    lod_file_count: int
    """Number of LOD files that were generated and uploaded."""

    status: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_entity_id(entity_id_str: str) -> UUID:
    """Parse and return a UUID, raising 400 on malformed input."""
    try:
        return UUID(entity_id_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Invalid entity_id '{entity_id_str}': not a valid UUID.",
            },
        ) from exc


def _validate_obj_extension(filename: str | None) -> None:
    """Raise 400 if the uploaded file is not an .obj."""
    ext = pathlib.Path(filename).suffix.lower() if filename else ""
    if ext != ".obj":
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Invalid file extension. Must be .obj",
            },
        )


def _preflight_size_check(file: UploadFile) -> None:
    """Fast-path size guard using the Content-Length header when available."""
    max_mb = MAX_FILE_SIZE / (1024 * 1024)
    if file.size is not None and file.size > MAX_FILE_SIZE:
        L.error(f"Mesh upload rejected: file too large (reported size {file.size} B).")
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Uploaded file is too large. Max size: {max_mb:.0f} MB.",
            },
        )


# ---------------------------------------------------------------------------
# Step 1 – upload original OBJ asset
# ---------------------------------------------------------------------------


def _register_obj_asset(
    client: entitysdk.client.Client,
    entity_id: UUID,
    obj_path: pathlib.Path,
) -> str:
    """Upload the raw OBJ file as an asset on the given EMCellMesh entity."""
    L.info(f"Uploading original OBJ asset for entity {entity_id} …")
    try:
        asset = client.upload_file(
            entity_id=entity_id,
            entity_type=EMCellMesh,
            file_path=obj_path,
            file_content_type=ContentType.application_obj,
            asset_label=AssetLabel.cell_surface_mesh,
        )
    except EntitySDKError as exc:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.ENTITYSDK_API_FAILURE,
                "detail": f"OBJ asset registration failed: {exc}",
            },
        ) from exc

    L.info(f"OBJ asset registered: {asset.id}")
    return str(asset.id)


# ---------------------------------------------------------------------------
# Step 2 – generate LOD meshes
# ---------------------------------------------------------------------------


def _generate_lods(obj_path: pathlib.Path, output_dir: pathlib.Path) -> dict[str, str]:
    """Run ultraliser LOD generation and return a {filename: abs_path} dict.

    Mirrors the notebook cells:
        mesh = ultraliser.Mesh(file_name=str(glb_path), verbose=False)
        generator = ultraliser.LODGenerator(mesh)
        generator.generate_web_lods(mesh_output_dir)
    """
    L.info(f"Generating LOD meshes from {obj_path} → {output_dir} …")
    output_dir.mkdir(parents=True, exist_ok=True)

    mesh = ultraliser.Mesh(file_name=str(obj_path), verbose=False)
    generator = ultraliser.LODGenerator(mesh)
    generator.generate_web_lods(str(output_dir))

    lod_files = {
        filename: os.path.join(str(output_dir), filename)
        for filename in os.listdir(str(output_dir))
        if os.path.isfile(os.path.join(str(output_dir), filename))
    }

    if not lod_files:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": "LOD_GENERATION_ERROR",
                "detail": "ultraliser produced no LOD output files.",
            },
        )

    L.info(f"Generated {len(lod_files)} LOD file(s): {list(lod_files.keys())}")
    return lod_files


# ---------------------------------------------------------------------------
# Step 3 – upload LOD directory
# ---------------------------------------------------------------------------


def _register_lod_directory(
    client: entitysdk.client.Client,
    entity_id: UUID,
    lod_files: dict[str, str],
) -> str:
    """Upload the LOD directory block.

    Mirrors the notebook cell:
        result = client.upload_directory(
            entity_id=cell_mesh_id,
            entity_type=EMCellMesh,
            name="lod-mesh-directory",
            paths=mesh_paths_dict,
            label="lod_mesh_block",
            metadata=None,
        )
    """
    L.info(f"Uploading {len(lod_files)} LOD file(s) for entity {entity_id} …")
    try:
        result = client.upload_directory(
            entity_id=entity_id,
            entity_type=EMCellMesh,
            name="lod-mesh-directory",
            paths=lod_files,
            label=AssetLabel.lod_mesh_block,
            metadata=None,
        )
    except EntitySDKError as exc:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.ENTITYSDK_API_FAILURE,
                "detail": f"LOD directory upload failed: {exc}",
            },
        ) from exc

    # result may be a single asset or a list depending on entitysdk version
    asset_id = str(result.id) if hasattr(result, "id") else str(result[0].id)
    L.info(f"LOD directory asset registered: {asset_id}")
    return asset_id


# ---------------------------------------------------------------------------
# Core pipeline (runs in a thread pool to avoid blocking the event loop)
# ---------------------------------------------------------------------------


def _run_registration_pipeline(
    client: entitysdk.client.Client,
    entity_id: UUID,
    obj_path: pathlib.Path,
) -> tuple[str, str, int]:
    """Execute the full registration pipeline synchronously.

    Returns
    -------
    (obj_asset_id, lod_directory_asset_id, lod_file_count)
    """
    with ExitStack() as stack:
        # Temporary directory for LOD output; cleaned up on exit
        lod_dir = pathlib.Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="lod_output_"))
        )

        # ── Step 1: upload original OBJ ──────────────────────────────────
        obj_asset_id = _register_obj_asset(client, entity_id, obj_path)

        # ── Step 2: generate LOD meshes ──────────────────────────────────
        lod_files = _generate_lods(obj_path, lod_dir)

        # ── Step 3: upload LOD directory ─────────────────────────────────
        lod_directory_asset_id = _register_lod_directory(client, entity_id, lod_files)

        return obj_asset_id, lod_directory_asset_id, len(lod_files)


# ---------------------------------------------------------------------------
# FastAPI endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/register-mesh",
    summary="Register an EM-cell OBJ mesh and generate/register LOD variants.",
    description=(
        "Accepts an .obj file and the ID of an existing EMCellMesh entity. "
        "Registers the OBJ as the primary surface-mesh asset, then generates "
        "web-compatible LOD meshes via ultraliser and uploads them as a "
        "directory block on the same entity."
    ),
)
async def mesh_registration(
    file: Annotated[UploadFile, File(description="OBJ mesh file to upload (.obj)")],
    client: Annotated[entitysdk.client.Client, Depends(get_client)],
    entity_id: Annotated[
        str,
        Form(description="UUID of the existing EMCellMesh entity to attach assets to"),
    ],
) -> MeshRegistrationResponse:
    """Register an OBJ mesh and its LOD variants against an existing EMCellMesh entity."""
    # ── Validation ───────────────────────────────────────────────────────
    _validate_obj_extension(file.filename)
    _preflight_size_check(file)
    entity_uuid = _validate_entity_id(entity_id)

    max_mb = MAX_FILE_SIZE / (1024 * 1024)
    temp_obj_path = ""

    try:
        # Save upload to a temp file (also enforces the streaming size limit)
        temp_obj_path = _save_upload_to_tempfile(file, suffix=".obj")

        if pathlib.Path(temp_obj_path).stat().st_size == 0:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail={
                    "code": ApiErrorCode.INVALID_REQUEST,
                    "detail": "Uploaded file is empty.",
                },
            )

        # Validate mesh geometry
        validate_mesh_reader(temp_obj_path)

        # Run the pipeline in a thread so we don't block the async event loop
        obj_asset_id, lod_directory_asset_id, lod_file_count = await run_in_threadpool(
            _run_registration_pipeline,
            client,
            entity_uuid,
            pathlib.Path(temp_obj_path),
        )

        _cleanup_temp_file(temp_obj_path)

        return MeshRegistrationResponse(
            entity_id=str(entity_uuid),
            obj_asset_id=obj_asset_id,
            lod_directory_asset_id=lod_directory_asset_id,
            lod_file_count=lod_file_count,
            status="success",
        )

    except FileTooLargeError:
        L.error(f"Mesh upload rejected: file too large (max {max_mb:.0f} MB).")
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Uploaded file is too large. Max size: {max_mb:.0f} MB.",
            },
        ) from None

    except HTTPException:
        _cleanup_temp_file(temp_obj_path)
        raise

    except (RuntimeError, ValueError) as exc:
        L.error(f"Mesh registration failed: {exc!s}")
        _cleanup_temp_file(temp_obj_path)
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Mesh registration failed: {exc!s}",
            },
        ) from exc

    except OSError as exc:
        L.error(f"File-system error during mesh registration: {exc!s}")
        _cleanup_temp_file(temp_obj_path)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "detail": f"Internal server error: {exc!s}",
            },
        ) from exc

    except Exception as exc:
        traceback.print_exc()
        _cleanup_temp_file(temp_obj_path)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": "UNEXPECTED_ERROR",
                "detail": f"Pipeline failed: {type(exc).__name__} – {exc!s}",
            },
        ) from exc
