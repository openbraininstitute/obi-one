from obi_one.modeling.core.block import Block

class Circuit(Block):
    """
    """
    circuit_path: str | list[str]
    node_set: str | list[str]