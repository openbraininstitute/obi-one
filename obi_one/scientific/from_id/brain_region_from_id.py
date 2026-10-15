from entitysdk.models import BrainRegion

from obi_one.core.entity_from_id import DBType, IdentifiableFromID


class BrainRegionFromID(IdentifiableFromID[BrainRegion]):
    entitysdk_type: DBType[BrainRegion] = BrainRegion
