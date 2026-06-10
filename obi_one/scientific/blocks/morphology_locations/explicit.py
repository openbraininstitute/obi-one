from typing import Annotated, override

import morphio
import numpy as np
import pandas  # noqa: ICN001
from pydantic import BaseModel, ConfigDict, Field

from obi_one.scientific.blocks.morphology_locations.base import MorphologyLocationsBlock
from obi_one.scientific.library.morphology_locations import (
    _PRE_IDX,
    _SEC_ID,
    _SEC_LOC,
    _SEC_TYP,
    _SEG_ID,
    _SEG_OFF,
    _SOM_PAD,
)

_LOCATION_COLUMNS = (
    _SEG_ID,
    _SEC_ID,
    _SEC_TYP,
    _SEG_OFF,
    _SOM_PAD,
    _PRE_IDX,
    _SEC_LOC,
)

_SectionID = Annotated[
    int,
    Field(
        ge=0,
        strict=True,
        title="Section ID",
        description="SONATA global section ID: 0 for soma, then nrn_order neurites.",
    ),
]
_NormalizedSectionOffset = Annotated[
    float,
    Field(
        ge=0.0,
        le=1.0,
        title="Normalized section offset",
        description="Normalized location along the section.",
    ),
]


class MorphologyLocationPoint(BaseModel):
    """A SONATA global section ID and normalized offset defining one location."""

    model_config = ConfigDict(extra="forbid")

    section_id: _SectionID
    offset: _NormalizedSectionOffset


def _neurite_section_for_id(morphology: morphio.Morphology, section_id: int) -> morphio.Section:
    try:
        return morphology.section(section_id - 1)
    except morphio.RawDataError:
        msg = f"Section ID {section_id} does not exist in the provided morphology."
        raise ValueError(msg) from None


def _section_length(section: morphio.Section) -> float:
    return float(np.linalg.norm(np.diff(section.points, axis=0), axis=1).sum())


def _point_on_section(
    morphology: morphio.Morphology, section_id: int, offset: float
) -> dict[str, int | float]:
    if section_id == 0:
        return {
            _SEG_ID: 0,
            _SEC_ID: 0,
            _SEC_TYP: int(morphio.SectionType.soma),
            _SEG_OFF: 0.0,
            _SOM_PAD: 0.0,
            _PRE_IDX: 0,
            _SEC_LOC: offset,
        }

    section = _neurite_section_for_id(morphology, section_id)
    segment_lengths = np.linalg.norm(np.diff(section.points, axis=0), axis=1)
    section_length = float(segment_lengths.sum())
    if section_length <= 0.0:
        msg = f"Section ID {section_id} has no positive-length segments."
        raise ValueError(msg)

    distance_on_section = offset * section_length
    cumulative_lengths = np.cumsum(segment_lengths)
    segment_id = min(
        int(np.searchsorted(cumulative_lengths, distance_on_section, side="right")),
        len(segment_lengths) - 1,
    )
    segment_start = 0.0 if segment_id == 0 else float(cumulative_lengths[segment_id - 1])

    path_distance = distance_on_section
    ancestor = section
    while not ancestor.is_root:
        ancestor = ancestor.parent
        path_distance += _section_length(ancestor)

    return {
        _SEG_ID: segment_id,
        _SEC_ID: section_id,
        _SEC_TYP: int(section.type),
        _SEG_OFF: distance_on_section - segment_start,
        _SOM_PAD: path_distance,
        _PRE_IDX: 0,
        _SEC_LOC: offset,
    }


class ExplicitMorphologyLocations(MorphologyLocationsBlock):
    """A deterministic collection of SONATA locations on an nrn_order morphology."""

    locations: tuple[MorphologyLocationPoint, ...] = Field(
        min_length=1,
        title="Explicit locations",
        description="Non-empty collection of section IDs and normalized offsets.",
    )

    def _make_points(self, morphology: morphio.Morphology) -> pandas.DataFrame:
        points = [
            _point_on_section(morphology, location.section_id, location.offset)
            for location in self.locations
        ]
        return pandas.DataFrame(points, columns=_LOCATION_COLUMNS)

    @override
    def _check_parameter_values(self) -> None:
        return None
