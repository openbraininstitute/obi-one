"""Configuration schemas for the level-of-detail (LOD) mesh generation pipeline."""

from pathlib import Path
from typing import Any, ClassVar
from uuid import UUID

from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field, PrivateAttr

from obi_one.core.base import OBIBaseModel


class MeshLodGenerationSingleConfig(OBIBaseModel):
    """Configuration schema for processing LOD mesh scans."""

    _single_task_config_type: ClassVar[TaskConfigType] = TaskConfigType.mesh_lod_generation__config
    _single_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.mesh_lod_generation__execution
    )

    idx: int = -1
    scan_output_root: Path = Path()
    coordinate_output_root: Path = Path()

    _single_entity: Any = PrivateAttr(default=None)

    entity_id: UUID = Field(
        ..., description="The unique identifier of the target EMCellMesh entity."
    )
    mesh_asset_id: UUID = Field(
        ..., description="The specific asset ID corresponding to the source mesh payload data."
    )
    mesh_format: str = Field(
        ..., description="The format of the source mesh asset ('obj' or 'glb')."
    )

    @property
    def single_entity(self) -> Any:
        return self._single_entity

    def set_single_entity(self, entity: Any) -> None:
        self._single_entity = entity


__all__ = ["MeshLodGenerationSingleConfig"]
