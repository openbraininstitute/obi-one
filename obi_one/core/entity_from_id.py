"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.core.entity_from_id import (
    abc,
    ClassVar,
    Entity,
    EntityFromID,
    entitysdk,
    Enum,
    Field,
    Identifiable,
    IdentifiableFromID,
    LoadAssetMethod,
    OBIBaseModel,
    PrivateAttr,
)

__all__ = [
    "abc",
    "ClassVar",
    "Entity",
    "EntityFromID",
    "entitysdk",
    "Enum",
    "Field",
    "Identifiable",
    "IdentifiableFromID",
    "LoadAssetMethod",
    "OBIBaseModel",
    "PrivateAttr",
]
