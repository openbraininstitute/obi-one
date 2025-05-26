from obi_one.core.base import OBIBaseModel


class NamedTuple(OBIBaseModel):
    """Helper class to assign a name to a tuple of elements."""

    name: str
    elements: tuple

    def __repr__(self):
        return self.name
