from enum import IntEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel


class Node(BaseModel):
    morphology_file: Annotated[
        str, Field(description="Path to the morphology file in the circuit's sonata directory")
    ]
    morphology_name: str | None
    position: Annotated[
        tuple[float, float, float], Field(description="Position coordinates (x,y,z)")
    ]
    orientation: Annotated[
        tuple[float, float, float, float], Field(description="Orientation quaternion (x, y, z, w)")
    ]
    soma_radius: float | None


Nodes = list[Node]


class MorphPath(BaseModel):
    path: Path
    format: Literal["asc", "h5", "swc"]


class MorphoViewerTreeItemType(IntEnum):
    Soma = 0
    Dendrite = 1
    BasalDendrite = 2
    ApicalDendrite = 3
    Myelin = 4
    Axon = 5
    Selected = 6
    Liaison = 7
    Unknown = 8


class Section(BaseModel):
    id: str
    parent_id: str | None
    type: MorphoViewerTreeItemType
    points: list[tuple[float, float, float]]
    radii: list[float]


class Sections(RootModel[list[Section]]):
    pass
