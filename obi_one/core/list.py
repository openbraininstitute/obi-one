from obi_one.core.base import OBIBaseModel


class NamedList(OBIBaseModel):
    """Helper class to assign a name to a list of elements."""

    name: str
    elements: tuple

    def __repr__(self):
        return self.name
