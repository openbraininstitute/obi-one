from enum import IntEnum
from pathlib import Path
from typing import Annotated, Literal, TypedDict

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


_SONATA_SECTION_ID_DESCRIPTION = (
    "SONATA global section ID: 0 for the soma, then nrn_order neurites — the id "
    "``MorphologyLocationPoint.section_id`` expects. It is the morphio section id plus one; "
    "``id`` above stays the raw morphio id, meaningful only for linking within this response."
)


class Section(BaseModel):
    id: str
    sonata_section_id: Annotated[int, Field(description=_SONATA_SECTION_ID_DESCRIPTION)]
    parent_id: str | None
    type: MorphoViewerTreeItemType
    points: list[tuple[float, float, float]]
    radii: list[float]


class SectionDict(TypedDict):
    id: str
    sonata_section_id: int
    parent_id: str | None
    type: MorphoViewerTreeItemType
    points: list[tuple[float, float, float]]
    radii: list[float]


class Sections(RootModel[list[Section]]):
    pass


_COORDINATES_DESCRIPTION = (
    "Afferent surface positions, flattened as ``[x0, y0, z0, x1, y1, z1, ...]`` — the layout "
    "the viewer uploads to the GPU as a single buffer."
)


class SynapseGroup(BaseModel):
    """Afferent synapses of one edge population, as recorded in the SONATA edge file.

    Positions are raw. SONATA computes a somatic synapse against a *spherical* soma, while a
    morphology describes the soma as a cylinder stack or a contour, so those coordinates sink
    inside — or float outside — the surface a viewer actually draws. A client that renders them
    has to project the somatic ones onto its own geometry, which is what ``section_ids`` selects
    and ``target_node_ids`` groups by.
    """

    population_name: str
    coordinates: Annotated[list[float], Field(description=_COORDINATES_DESCRIPTION)]
    section_ids: Annotated[
        list[int],
        Field(
            description=(
                "SONATA section each synapse sits on, aligned with the positions. Section 0 is "
                "the soma, and those are the positions that need projecting."
            )
        ),
    ]
    target_node_ids: Annotated[
        list[int],
        Field(description="Node each synapse targets, aligned with the positions."),
    ]


class SynapseGroups(RootModel[list[SynapseGroup]]):
    pass
