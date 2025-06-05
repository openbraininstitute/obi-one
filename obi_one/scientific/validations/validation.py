from pydantic import BaseModel
import abc

class Validation(BaseModel, abc.ABC):

    """Base class for validation objects.

    This class is used to define the structure of validation objects.
    It can be extended to create specific validation types.
    """
    name: str
    description: str | None = None

    def run(self) -> None:
        """Validate the provided data against the validation rules."""
        raise NotImplementedError("Subclasses must implement this method.")



    def save(self) -> None:
        """Make a call to entitysdk to save the result of the validation."""
        raise NotImplementedError("Subclasses must implement this method.")