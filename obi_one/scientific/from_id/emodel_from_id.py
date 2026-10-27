from entitysdk.models import EModel

from obi_one.core.entity_from_id import EntityFromID


class EModelFromID(EntityFromID[EModel]):
    _entitysdk_type: type[EModel] = EModel
