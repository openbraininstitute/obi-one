"""Configuration schemas for the level-of-detail (LOD) mesh generation pipeline."""

from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import Field, PrivateAttr

from obi_one.core.base import OBIBaseModel


class MeshLodGenerationSingleConfig(OBIBaseModel):
    """Configuration schema for processing LOD mesh scans."""

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
