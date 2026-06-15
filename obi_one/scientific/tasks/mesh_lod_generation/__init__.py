"""Level of detail (LOD) mesh generation task pipeline."""

from obi_one.scientific.tasks.mesh_lod_generation.config import (
    MeshLodGenerationScanConfig,
    MeshLodGenerationSingleConfig,
)
from obi_one.scientific.tasks.mesh_lod_generation.task import MeshLODGenerationTask

__all__ = [
    "MeshLODGenerationTask",
    "MeshLodGenerationScanConfig",
    "MeshLodGenerationSingleConfig",
]
