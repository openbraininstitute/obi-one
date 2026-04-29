from pydantic import Field

from obi_one.core.tuple import NamedTuple
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID


class CellMorphologyNamedTuple(NamedTuple):
    elements: tuple[CellMorphologyFromID, ...] = Field(min_length=1)


class MEModelNamedTuple(NamedTuple):
    elements: tuple[MEModelFromID, ...] = Field(min_length=1)


class CellMorphologyAndMEModelNamedTuple(NamedTuple):
    elements: tuple[CellMorphologyFromID | MEModelFromID, ...] = Field(min_length=1)
