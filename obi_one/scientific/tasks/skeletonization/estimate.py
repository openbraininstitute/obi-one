"""Cost estimation for skeletonization tasks."""

import tempfile
from pathlib import Path
from uuid import UUID

import pylmesh
from entitysdk import models
from entitysdk.client import Client
from entitysdk.types import AssetLabel, FetchFileStrategy

from obi_one.scientific.from_id.em_cell_mesh_from_id import EMCellMeshFromID
from obi_one.scientific.tasks.skeletonization.config import SkeletonizationSingleConfig


def _compute_mesh_surface_area(db_client: Client, cell_mesh: EMCellMeshFromID) -> float:
    """Download the mesh asset and compute its surface area.

    Uses S3 mount if available, otherwise downloads the file.

    Args:
        db_client: Database client for fetching assets.
        cell_mesh: The cell mesh reference.

    Returns:
        The surface area of the mesh.
    """
    em_cell_mesh = db_client.get_entity(
        entity_id=cell_mesh.id_str,
        entity_type=models.EMCellMesh,
    )

    # Find the cell_surface_mesh asset
    asset = next(
        (a for a in em_cell_mesh.assets if a.label == AssetLabel.cell_surface_mesh),
        None,
    )
    if asset is None:
        msg = f"No cell_surface_mesh asset found for EMCellMesh {cell_mesh.id_str}"
        raise ValueError(msg)

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / f"{asset.id}.glb"
        db_client.fetch_file(
            entity_id=em_cell_mesh.id,
            entity_type=models.EMCellMesh,
            asset_id=asset.id,
            output_path=output_path,
            strategy=FetchFileStrategy.link_or_download,
        )

        mesh = pylmesh.load_mesh(str(output_path))
        return mesh.surface_area()


def estimate_skeletonization_count(
    *,
    db_client: Client,
    config_id: UUID,
) -> int:
    """Estimate the count for skeletonization cost calculation.

    The count is based on the total surface area of all cell meshes
    in the configuration.

    Args:
        db_client: Database client for fetching the config.
        config_id: UUID of the skeletonization config.

    Returns:
        The count to use for cost estimation (based on surface area).
    """
    config = db_client.get_task_config(
        config_id=config_id,
        config_type=SkeletonizationSingleConfig,
    )
    cell_mesh = config.initialize.cell_mesh

    if isinstance(cell_mesh, list):
        total_area = sum(
            _compute_mesh_surface_area(db_client, mesh) for mesh in cell_mesh
        )
    else:
        total_area = _compute_mesh_surface_area(db_client, cell_mesh)

    # Convert surface area to count (you may want to adjust this formula)
    return max(0, total_area)
