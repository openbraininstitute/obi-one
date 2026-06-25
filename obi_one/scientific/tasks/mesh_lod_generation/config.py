"""Configuration schemas for the level-of-detail (LOD) mesh generation pipeline."""

from typing import ClassVar
from uuid import UUID

from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.single import SingleConfigMixin, SingleCoordinateScanParams


class MeshLodGenerationSingleConfig(OBIBaseModel, SingleConfigMixin):
    """Configuration schema for processing LOD mesh scans."""

    _single_task_config_type: ClassVar[TaskConfigType] = TaskConfigType.mesh_lod_generation__config
    _single_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.mesh_lod_generation__execution
    )

    # SingleConfigMixin declares this as `SingleCoordinateScanParams = None` which
    # works fine as a plain class attribute but fails Pydantic validation when None
    # is passed (annotation doesn't include None). Override with an explicit Optional.
    single_coordinate_scan_params: SingleCoordinateScanParams | None = Field(default=None)

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


__all__ = [
    "MeshLodGenerationSingleConfig",
]
