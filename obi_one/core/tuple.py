from pydantic import NonNegativeInt

from obi_one.core.base import OBIBaseModel


class NamedTuple(OBIBaseModel):
    """Helper class to assign a name to a tuple of elements."""

    name: str
    elements: tuple[NonNegativeInt, ...]

    def __repr__(self) -> str:
        """Return a string representation of the NamedTuple."""
        return self.name
