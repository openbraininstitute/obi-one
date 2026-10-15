from entitysdk.models import BrainRegion
from pydantic import Field

from obi_one.core.entity_from_id import IdentifiableFromID


class BrainRegionFromID(IdentifiableFromID[BrainRegion]):
    entitysdk_type: type[BrainRegion] = Field(default=BrainRegion, exclude=True, repr=False)
