import abc
from typing import ClassVar

from pydantic import BaseModel

from obi_one.core.activity import Activity


class Validation(Activity, abc.ABC):
    """Base class for validation objects.

    This class is used to define the structure of validation objects.
    It can be extended to create specific validation types.
    """