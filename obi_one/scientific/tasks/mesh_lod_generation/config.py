"""Configuration schemas for the level-of-detail (LOD) mesh generation pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from uuid import UUID


class MeshLodGenerationSingleConfig(BaseModel):
    """Configuration schema for processing LOD mesh scans."""

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
