"""Cost estimation for skeletonization tasks."""

import json
import math
import struct
import tempfile
from pathlib import Path
from uuid import UUID

import DracoPy
import numpy as np
import trimesh
from entitysdk import models
from entitysdk.client import Client
from entitysdk.types import AssetLabel, ContentType, FetchFileStrategy

from obi_one.scientific.from_id.em_cell_mesh_from_id import EMCellMeshFromID
from obi_one.scientific.tasks.skeletonization.config import SkeletonizationSingleConfig
from obi_one.utils.db_sdk import get_entity_asset_by_label


def _load_glb_mesh(path: str) -> trimesh.Trimesh:
    """Load a GLB file into a Trimesh, handling Draco compression if present."""
    mesh = trimesh.load(path, force="mesh")
    if mesh.vertices.any():
        return mesh

    # Draco-compressed GLB: manually decode
    data = Path(path).read_bytes()
    chunk_length = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20 : 20 + chunk_length])

    bin_offset = 20 + chunk_length
    bin_chunk_length = struct.unpack("<I", data[bin_offset : bin_offset + 4])[0]
    bin_data = data[bin_offset + 8 : bin_offset + 8 + bin_chunk_length]

    draco_ext = gltf["meshes"][0]["primitives"][0]["extensions"][
        "KHR_draco_mesh_compression"
    ]
    bv = gltf["bufferViews"][draco_ext["bufferView"]]
    decoded = DracoPy.decode(bin_data[bv["byteOffset"] : bv["byteOffset"] + bv["byteLength"]])

    return trimesh.Trimesh(
        vertices=np.array(decoded.points).reshape(-1, 3),
        faces=np.array(decoded.faces).reshape(-1, 3),
    )


def _compute_mesh_surface_area(db_client: Client, cell_mesh: EMCellMeshFromID) -> float:
    """Download the mesh asset and compute its surface area.

    Args:
        db_client: Database client for fetching assets.
        cell_mesh: The cell mesh reference.

    Returns:
        The surface area of the mesh.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "mesh.glb"
        db_client.fetch_assets(
            entity_or_id=(cell_mesh.id_str, models.EMCellMesh),
            selection={
                "label": AssetLabel.cell_surface_mesh,
                "content_type": ContentType.model_gltf_binary,
            },
            output_path=output_path,
            strategy=FetchFileStrategy.link_or_download,
        ).one()

        mesh = _load_glb_mesh(str(output_path))
        # convert to um2
        return mesh.area * 1e-6


def _get_skeletonization_config(
    db_client: Client,
    config_id: UUID,
) -> SkeletonizationSingleConfig:
    """Fetch and parse a skeletonization config from the database.

    Args:
        db_client: Database client for fetching the config.
        config_id: UUID of the skeletonization config.

    Returns:
        The parsed SkeletonizationSingleConfig.
    """
    task_config = db_client.get_entity(
        entity_id=config_id,
        entity_type=models.TaskConfig,
    )

    # Find the task_config asset
    asset = get_entity_asset_by_label(
        client=db_client, config=task_config, asset_label=AssetLabel.task_config
    )

    # Download and parse the config JSON
    config_bytes = db_client.download_content(
        entity_id=config_id,
        entity_type=models.TaskConfig,
        asset_id=asset.id,
    )
    config_dict = json.loads(config_bytes.decode("utf-8"))

    return SkeletonizationSingleConfig.model_validate(config_dict)


def estimate_skeletonization_count(
    *,
    db_client: Client,
    config_id: UUID,
) -> int:
    """Estimate the count for skeletonization cost calculation.

    The count is based on the surface area of the cell mesh
    in the configuration.

    Args:
        db_client: Database client for fetching the config.
        config_id: UUID of the skeletonization config.

    Returns:
        The count to use for cost estimation (based on surface area).
    """
    config = _get_skeletonization_config(db_client, config_id)
    cell_mesh = config.initialize.cell_mesh
    total_area = _compute_mesh_surface_area(db_client, cell_mesh)

    return max(1, math.ceil(total_area))
