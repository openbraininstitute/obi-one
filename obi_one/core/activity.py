import abc
from typing import ClassVar

from pydantic import BaseModel


class Activity(BaseModel, abc.ABC):
    """Base class for validation objects.

    This class is used to define the structure of validation objects.
    It can be extended to create specific validation types.
    """

    name: ClassVar[str]
    description: ClassVar[str]

    def run(self) -> None:
        """Validate the provided data against the validation rules."""
        msg = "Subclasses must implement this method."
        raise NotImplementedError(msg)

    def save(self) -> None:
        """Make a call to entitysdk to save the result of the validation."""
        msg = "Subclasses must implement this method."
        raise NotImplementedError(msg)
