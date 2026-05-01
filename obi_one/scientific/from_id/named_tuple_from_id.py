from pydantic import Field

from obi_one.core.tuple import NamedTuple
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID


class EMSynapseMappingInputNamedTuple(NamedTuple):
    elements: tuple[CellMorphologyFromID | MEModelFromID, ...] = Field(min_length=1)
