from typing import Any

from pydantic import NonNegativeInt

from obi_one.core.base import OBIBaseModel


class NamedTupleBase(OBIBaseModel):
    """Helper class to assign a name to a tuple of elements."""

    name: str = "Default name"
    elements: tuple[Any, ...]

    def __repr__(self) -> str:
        """Return a string representation of the NamedTuple."""
        return self.name

    def __len__(self) -> int:
        """Return the number of elements in the NamedTuple."""
        return len(self.elements)

    def __getitem__(self, index: int) -> Any:
        """Return the element at the specified index."""
        return self.elements[index]


class NamedTuple(NamedTupleBase):
    """Helper class to assign a name to a tuple of elements."""

    elements: tuple[NonNegativeInt, ...]
