from typing import Any, ClassVar
from typing_extensions import Annotated

from pydantic import Field

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.compartment_sets import CompartmentSet


CompartmentSetUnion = Annotated[
    CompartmentSet,
    Field(discriminator="type"),
]


class CompartmentSetReference(BlockReference):
    """A reference to a block that provides a named compartment set."""

    allowed_block_types: ClassVar[Any] = CompartmentSetUnion


def resolve_compartment_set_ref_to_name(
    comp_ref: CompartmentSetReference | str | None, default: str | None = None
) -> str | None:
    if comp_ref is None:
        return default
    if isinstance(comp_ref, str):
        return comp_ref
    return comp_ref.block.block_name