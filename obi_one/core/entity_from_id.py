from enum import Enum
from uuid import UUID

from entitysdk.client import Client as DBClient
from entitysdk.models.entity import Entity, Identifiable
from pydantic import Field, PrivateAttr

from obi_one.core.base import OBIBaseModel


class LoadAssetMethod(Enum):
    MEMORY = "memory"
    FILE = "file"


class EntityFromID[TEntity: Entity](OBIBaseModel):
    """Base class for entity references that resolve to full Entity objects (with assets)."""

    id_str: str = Field(description="ID of the entity in string format.")
    _entity: TEntity | None = PrivateAttr(default=None)
    entitysdk_type: type[TEntity] = Field(exclude=True, repr=False)

    def entity(self, db_client: DBClient) -> TEntity:
        if self._entity is None:
            self._entity = db_client.get_entity(
                entity_id=UUID(self.id_str),
                entity_type=self.entitysdk_type,
            )
        return self._entity

    def __str__(self) -> str:
        """Returns a string representation."""
        return f"{self.__class__.__name__}_{self.id_str}"


class IdentifiableFromID[TIdentifiable: Identifiable](OBIBaseModel):
    """Base class for references to Identifiable objects (controlled vocabularies like Species, BrainRegion, EType).

    These are not full Entity objects (no assets), but they are identifiable
    database records that can be fetched by ID.
    """  # ruff: ignore[line-too-long]

    id_str: str = Field(description="ID of the identifiable in string format.")
    _entity: TIdentifiable | None = PrivateAttr(default=None)
    entitysdk_type: type[TIdentifiable] = Field(exclude=True, repr=False)

    def entity(self, db_client: DBClient) -> TIdentifiable:
        if self._entity is None:
            self._entity = db_client.get_entity(
                entity_id=UUID(self.id_str),
                entity_type=self.entitysdk_type,
            )
        return self._entity

    def __str__(self) -> str:
        """Returns a string representation."""
        return f"{self.__class__.__name__}_{self.id_str}"
