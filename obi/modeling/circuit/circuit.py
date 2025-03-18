from obi.modeling.core.block import Block
from obi.modeling.core.base import OBIBaseModel

class CircuitPath(OBIBaseModel):
    name: str
    path: str

    def __repr__(self):
        return self.name


class Circuit(Block):
    """
    """
    circuit_path: str | list[str]
    node_set: str | list[str]