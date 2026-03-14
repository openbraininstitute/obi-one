import abc
from typing import ClassVar

from obi_one.core.base import OBIBaseModel
from obi_one.core.schema import SchemaKey


class Task(OBIBaseModel, abc.ABC):
    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: False,
    }
