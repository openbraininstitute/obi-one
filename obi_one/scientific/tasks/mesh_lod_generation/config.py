"""Configuration schemas for the level-of-detail (LOD) mesh generation pipeline."""

from uuid import UUID

from pydantic import BaseModel, Field


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


MeshLodGenerationSingleConfig.model_rebuild(_types_namespace={"UUID": UUID})

__all__ = [
    "MeshLodGenerationSingleConfig",
]
