from typing import ClassVar

from entitysdk.models import BrainRegion

from obi_one.core.entity_from_id import IdentifiableFromID


class BrainRegionFromID(IdentifiableFromID[BrainRegion]):
    entitysdk_class: ClassVar[type[BrainRegion]] = BrainRegion
