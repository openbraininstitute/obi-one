from pathlib import Path
from typing import ClassVar

import morphio
import neurom
from entitysdk.models import Circuit
from entitysdk.models.entity import Entity
from pydantic import PrivateAttr

from obi_one.database.db_manager import db
from obi_one.database.entity_from_id import EntityFromID, LoadAssetMethod

import io

class CircuitFromID(EntityFromID):
    entitysdk_class: ClassVar[type[Entity]] = Circuit
    _entity: Circuit | None = PrivateAttr(default=None)
