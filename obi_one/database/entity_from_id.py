import abc
from typing import ClassVar

from entitysdk.models.entity import Entity
from pydantic import Field, PrivateAttr

from obi_one.database.db_manager import db
from obi_one.core.base import OBIBaseModel


class EntityFromID(OBIBaseModel, abc.ABC):
    entitysdk_class: ClassVar[type[Entity]] = None
    id_str: str = Field(description="ID of the entity in string format.")
    _entity: Entity | None = PrivateAttr(default=None)

    @classmethod
    def fetch(cls, entity_id: str) -> Entity:
        return db.client.get_entity(
            entity_id=entity_id, entity_type=cls.entitysdk_class, token=db.token
        )

    @classmethod
    def find(cls, limit: int = 10, **kwargs) -> list[Entity]:
        return db.client.search_entity(
            entity_type=cls.entitysdk_class, query=kwargs, token=db.token, limit=limit
        ).all()

    @property
    def entity(self) -> Entity:
        if self._entity is None:
            self._entity = self.__class__.fetch(self.id_str)
        return self._entity

    @property
    def entitysdk_type(self) -> type[Entity]:
        return self.__class__.entitysdk_class
