import abc
from typing import ClassVar

from obi_one.core.base import OBIBaseModel
from obi_one.core.schema import SchemaKey


class Task(OBIBaseModel, abc.ABC):
    pass
