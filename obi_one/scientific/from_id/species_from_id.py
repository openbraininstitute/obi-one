from typing import ClassVar

from entitysdk.models import Species

from obi_one.core.entity_from_id import IdentifiableFromID


class SpeciesFromID(IdentifiableFromID[Species]):
    entitysdk_class: ClassVar[type[Species]] = Species
