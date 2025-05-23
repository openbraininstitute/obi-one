from obi_one.core.base import OBIBaseModel


class NamedPath(OBIBaseModel):
    """Helper class to assign a name to a file path."""

    name: str
    path: str

    def __repr__(self) -> str:
        """Return a string representation of the NamedPath object."""
        return self.name
