from typing import Annotated, Literal

from pydantic import BaseModel, Field
from pathlib import Path


class Node(BaseModel):
    morphology_file: Annotated[
        str, Field(description="Path to the morphology file in the circuit's sonata directory")
    ]
    morphology_name: str
    position: Annotated[
        tuple[float, float, float], Field(description="Position coordinates (x,y,z)")
    ]
    orientation: Annotated[
        tuple[float, float, float, float], Field(description="Orientation quaternion (x, y, z, w)")
    ]
    soma_radius: float | None


Nodes = list[Node]


class NeuronSectionInfo(BaseModel):
    """Follows the interface defined in
    https://github.com/openbraininstitute/core-web-app/blob/3c09493d1b786aa2c7573305e4410841ef269e05/src/services/bluenaas-single-cell/types.ts.
    """

    index: int
    name: str
    nseg: int
    distance_from_soma: float
    sec_length: float
    xstart: list[float]
    xend: list[float]
    xcenter: list[float]
    xdirection: list[float]
    ystart: list[float]
    yend: list[float]
    ycenter: list[float]
    ydirection: list[float]
    zstart: list[float]
    zend: list[float]
    zcenter: list[float]
    zdirection: list[float]
    diam: list[float]
    length: list[float]
    distance: list[float]
    segment_distance_from_soma: list[float]
    segx: list[float]
    neuron_section_id: int
    neuron_segments_offset: list[int]
    parent_index: int


Morphology = dict[str, NeuronSectionInfo]


class MorphPath(BaseModel):
    path: Path
    format: Literal["asc", "h5", "swc"]
