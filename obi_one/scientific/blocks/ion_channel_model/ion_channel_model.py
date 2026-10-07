"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.ion_channel_model.ion_channel_model import (
    Block,
    ClassVar,
    EntityType,
    Field,
    IonChannelModelFromID,
    IonChannelModelWithConductance,
    IonChannelModelWithMaxPermeability,
    IonChannelModelWithoutConductance,
    NonNegativeFloat,
    SchemaKey,
    UIElement,
    Units,
)

__all__ = [
    "Block",
    "ClassVar",
    "EntityType",
    "Field",
    "IonChannelModelFromID",
    "IonChannelModelWithConductance",
    "IonChannelModelWithMaxPermeability",
    "IonChannelModelWithoutConductance",
    "NonNegativeFloat",
    "SchemaKey",
    "UIElement",
    "Units",
]
