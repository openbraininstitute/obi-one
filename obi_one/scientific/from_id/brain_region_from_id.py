from entitysdk.models import BrainRegion

from obi_one.core.entity_from_id import IdentifiableFromID


class BrainRegionFromID(IdentifiableFromID[BrainRegion]):
    @classmethod
    def entitysdk_class(cls) -> type[BrainRegion]:
        return BrainRegion
