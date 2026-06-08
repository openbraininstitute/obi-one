from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from uuid import UUID

from obi_one.core.scan_config import ScanConfig
from obi_one.types import TaskType


class MeshLodGenerationScanConfig(ScanConfig):
    """Configuration for generating LOD meshes from a registered EM-cell OBJ asset."""

    name: ClassVar[str] = "Mesh LOD Generation"
    description: ClassVar[str] = (
        "Generates web-compatible Level-of-Detail meshes from a registered EM-cell OBJ "
        "asset using ultraliser and uploads them as a directory block on the same entity."
    )

    task_type: TaskType = TaskType.mesh_lod_generation

    entity_id: UUID
    """The EMCellMesh entity to attach the generated LOD assets to."""

    obj_asset_id: UUID
    """The asset ID of the source OBJ file to generate LODs from."""
