from typing import ClassVar

import entitysdk
from entitysdk.models import ETypeClass
from pydantic import PrivateAttr

from obi_one.core.entity_from_id import IdentifiableFromID


class ETypeClassFromID(IdentifiableFromID):
    entitysdk_class: ClassVar[type[ETypeClass]] = ETypeClass
    _entity: ETypeClass | None = PrivateAttr(default=None)

    def entity(self, db_client: entitysdk.client.Client) -> ETypeClass:
        super().entity(db_client=db_client)
        return self._entity
