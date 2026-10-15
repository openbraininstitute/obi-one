from entitysdk.models import BrainRegion

from obi_one.core.entity_from_id import IdentifiableFromID


class BrainRegionFromID(IdentifiableFromID[BrainRegion]):
    _entitysdk_type: type[BrainRegion] = BrainRegion
