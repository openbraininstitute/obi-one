from pydantic import BaseModel

class Circuit(BaseModel):
    """
    """
    circuit_path: str | list[str]
    node_set: str | list[str]