import abc
from enum import Enum
from typing import ClassVar

import entitysdk
from entitysdk.models.entity import Entity
from pydantic import Field, PrivateAttr

from obi_one.core.base import OBIBaseModel


class LoadAssetMethod(Enum):
    MEMORY = "memory"
    FILE = "file"


class EntityFromID(OBIBaseModel, abc.ABC):
    entitysdk_class: ClassVar[type[Entity]] = None
    id_str: str = Field(description="ID of the entity in string format.")
    _entity: Entity | None = PrivateAttr(default=None)

    @classmethod
    def fetch(cls, entity_id: str, db_client: entitysdk.client.Client) -> Entity:
        return db_client.get_entity(entity_id=entity_id, entity_type=cls.entitysdk_class)

    def entity(self, db_client: entitysdk.client.Client) -> Entity:
        if self._entity is None:
            self._entity = self.__class__.fetch(self.id_str, db_client=db_client)
        return self._entity

    @property
    def entitysdk_type(self) -> type[Entity]:
        return self.__class__.entitysdk_class
