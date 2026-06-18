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
    obj_asset_id: UUID = Field(
        ...,
        description="The specific asset ID corresponding to the source OBJ payload data.",
    )


__all__ = [
    "MeshLodGenerationSingleConfig",
]
