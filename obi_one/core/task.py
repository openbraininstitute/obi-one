import abc
from typing import ClassVar

from obi_one.core.base import OBIBaseModel


class Task(OBIBaseModel, abc.ABC):
    json_schema_extra_additions: ClassVar[dict] = {
        "ui_enabled": False,
    }
