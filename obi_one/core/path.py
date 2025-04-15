from obi_one.core.base import OBIBaseModel

class NamedPath(OBIBaseModel):
    """Helper class to assign a name to a file path."""
    name: str
    path: str

    def __repr__(self):
        return self.name
