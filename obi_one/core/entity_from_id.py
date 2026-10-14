import abc
from enum import Enum
from typing import ClassVar

import entitysdk
from entitysdk.models.entity import Entity, Identifiable
from pydantic import Field, PrivateAttr

from obi_one.core.base import OBIBaseModel


class LoadAssetMethod(Enum):
    MEMORY = "memory"
    FILE = "file"


class EntityFromID[TEntity: Entity](OBIBaseModel, abc.ABC):
    """Base class for entity references that resolve to full Entity objects (with assets)."""

    entitysdk_class: ClassVar[type[TEntity]]
    id_str: str = Field(description="ID of the entity in string format.")
    _entity: TEntity | None = PrivateAttr(default=None)

    @classmethod
    def fetch(cls, entity_id: str, db_client: entitysdk.client.Client) -> TEntity:
        return db_client.get_entity(entity_id=entity_id, entity_type=cls.entitysdk_class)  # ty:ignore[invalid-argument-type]

    def entity(self, db_client: entitysdk.client.Client) -> TEntity:
        if self._entity is None:
            self._entity = self.__class__.fetch(self.id_str, db_client=db_client)
        if self._entity is None:
            msg = f"{self.__class__.__name__} failed to resolve entity {self.id_str!r}"
            raise RuntimeError(msg)
        return self._entity

    @property
    def entitysdk_type(self) -> type[TEntity]:
        return self.__class__.entitysdk_class

    def __str__(self) -> str:
        """Returns a string representation."""
        return f"{self.__class__.__name__}_{self.id_str}"


class IdentifiableFromID[TIdentifiable: Identifiable](OBIBaseModel, abc.ABC):
    """Base class for references to Identifiable objects (controlled vocabularies like Species, BrainRegion, EType).

    These are not full Entity objects (no assets), but they are identifiable
    database records that can be fetched by ID.
    """  # ruff: ignore[line-too-long]

    entitysdk_class: ClassVar[type[TIdentifiable]]
    id_str: str = Field(description="ID of the identifiable in string format.")
    _entity: TIdentifiable | None = PrivateAttr(default=None)

    @classmethod
    def fetch(cls, entity_id: str, db_client: entitysdk.client.Client) -> TIdentifiable:
        return db_client.get_entity(entity_id=entity_id, entity_type=cls.entitysdk_class)  # ty:ignore[invalid-argument-type]

    def entity(self, db_client: entitysdk.client.Client) -> TIdentifiable:
        if self._entity is None:
            self._entity = self.__class__.fetch(self.id_str, db_client=db_client)
        if self._entity is None:
            msg = f"{self.__class__.__name__} failed to resolve entity {self.id_str!r}"
            raise RuntimeError(msg)
        return self._entity

    def __str__(self) -> str:
        """Returns a string representation."""
        return f"{self.__class__.__name__}_{self.id_str}"
