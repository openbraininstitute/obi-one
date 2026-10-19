from entitysdk.models import Strain

from obi_one.core.entity_from_id import IdentifiableFromID


class StrainFromID(IdentifiableFromID[Strain]):
    _entitysdk_type: type[Strain] = Strain
