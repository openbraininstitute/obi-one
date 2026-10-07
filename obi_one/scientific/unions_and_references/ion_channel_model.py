"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.unions_and_references.ion_channel_model import (
    Annotated,
    Any,
    BlockReference,
    ClassVar,
    Discriminator,
    IonChannelModelReference,
    IonChannelModelUnion,
    IonChannelModelWithConductance,
    IonChannelModelWithMaxPermeability,
    IonChannelModelWithoutConductance,
)

from obi_one_lazy.scientific.unions_and_references.ion_channel_model import (
    _ION_CHANNEL_MODELS,
)

__all__ = [
    "Annotated",
    "Any",
    "BlockReference",
    "ClassVar",
    "Discriminator",
    "IonChannelModelReference",
    "IonChannelModelUnion",
    "IonChannelModelWithConductance",
    "IonChannelModelWithMaxPermeability",
    "IonChannelModelWithoutConductance",
    "_ION_CHANNEL_MODELS",
]
