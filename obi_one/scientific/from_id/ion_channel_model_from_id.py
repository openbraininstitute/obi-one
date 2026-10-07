"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.from_id.ion_channel_model_from_id import (
    ClassVar,
    ContentType,
    create_dir,
    Entity,
    EntityFromID,
    entitysdk,
    IonChannelModel,
    IonChannelModelFromID,
    Path,
    PrivateAttr,
)

__all__ = [
    "ClassVar",
    "ContentType",
    "create_dir",
    "Entity",
    "EntityFromID",
    "entitysdk",
    "IonChannelModel",
    "IonChannelModelFromID",
    "Path",
    "PrivateAttr",
]
