"""Unions and references of the NeuroMechFly closed-loop blocks kept in dictionaries."""

from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.neuromechfly.closed_loop import (
    BodyForce,
    LegOverride,
    OdourSource,
    Wall,
)

# ScanConfig reads a dictionary's block classes from a discriminated union, even of one class.
OdourSourceUnion = Annotated[OdourSource, Discriminator("type")]
WallUnion = Annotated[Wall, Discriminator("type")]
BodyForceUnion = Annotated[BodyForce, Discriminator("type")]
LegOverrideUnion = Annotated[LegOverride, Discriminator("type")]


class OdourSourceReference(BlockReference):
    """A reference to an OdourSource block."""

    allowed_block_types: ClassVar[Any] = OdourSourceUnion

    json_schema_extra_additions: ClassVar[dict] = {"allowed_block_types": [OdourSource.__name__]}


class WallReference(BlockReference):
    """A reference to a Wall block."""

    allowed_block_types: ClassVar[Any] = WallUnion

    json_schema_extra_additions: ClassVar[dict] = {"allowed_block_types": [Wall.__name__]}


class BodyForceReference(BlockReference):
    """A reference to a BodyForce block."""

    allowed_block_types: ClassVar[Any] = BodyForceUnion

    json_schema_extra_additions: ClassVar[dict] = {"allowed_block_types": [BodyForce.__name__]}


class LegOverrideReference(BlockReference):
    """A reference to a LegOverride block."""

    allowed_block_types: ClassVar[Any] = LegOverrideUnion

    json_schema_extra_additions: ClassVar[dict] = {"allowed_block_types": [LegOverride.__name__]}
