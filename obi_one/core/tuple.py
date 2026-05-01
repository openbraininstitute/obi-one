from pydantic import NonNegativeInt

from obi_one.core.base import OBIBaseModel


class NamedTuple(OBIBaseModel):
    """Helper class to assign a name to a tuple of elements."""

    name: str = "Default name"
    elements: tuple[NonNegativeInt, ...]

    def __repr__(self) -> str:
        """Return a string representation of the NamedTuple."""
        return self.name
    
    def __iter__(self):
        """Return an iterator over the elements of the NamedTuple."""
        return iter(self.elements)
    
    def __len__(self):
        """Return the number of elements in the NamedTuple."""
        return len(self.elements)
    
    def __getitem__(self, index):
        """Return the element at the specified index."""
        return self.elements[index]
