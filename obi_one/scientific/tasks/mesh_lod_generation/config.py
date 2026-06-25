"""Configuration schemas for the level-of-detail (LOD) mesh generation pipeline."""

from typing import ClassVar
from uuid import UUID

from pydantic import Field

from obi_one.core.single import SingleConfigMixin
from obi_one.types import TaskActivityType, TaskConfigType


class MeshLodGenerationSingleConfig(SingleConfigMixin):
    """Configuration schema for processing LOD mesh scans."""

    _single_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.mesh_lod_generation__config
    )
    _single_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.mesh_lod_generation__execution
    )

    entity_id: UUID = Field(
        ...,
        description="The unique identifier of the target EMCellMesh entity.",
    )
    mesh_asset_id: UUID = Field(
        ...,
        description="The specific asset ID corresponding to the source mesh payload data.",
    )
    mesh_format: str = Field(
        ...,
        description="The format of the source mesh asset ('obj' or 'glb').",
    )


MeshLodGenerationSingleConfig.model_rebuild(_types_namespace={"UUID": UUID})

__all__ = [
    "MeshLodGenerationSingleConfig",
]
