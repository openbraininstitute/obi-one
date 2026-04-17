"""Cost estimation for skeletonization tasks."""

import json
import math
import tempfile
from pathlib import Path
from uuid import UUID

import pylmesh
from entitysdk import models
from entitysdk.client import Client
from entitysdk.types import AssetLabel, ContentType, FetchFileStrategy

from obi_one.scientific.from_id.em_cell_mesh_from_id import EMCellMeshFromID
from obi_one.scientific.tasks.skeletonization.config import SkeletonizationSingleConfig


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
        db_client.fetch_asset(
            entity_or_id=cell_mesh.id_str,
            entity_type=models.EMCellMesh,
            selection={
                "label": AssetLabel.cell_surface_mesh,
                "content_type": ContentType.model_gltf_binary,
            },
            output_path=output_path,
            strategy=FetchFileStrategy.link_or_download,
        )

        mesh = pylmesh.load_mesh(str(output_path))
        return mesh.surface_area()


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
    asset = next(
        (a for a in task_config.assets if a.label == AssetLabel.task_config),
        None,
    )
    if asset is None:
        msg = f"No task_config asset found for TaskConfig {config_id}"
        raise ValueError(msg)

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
