from typing import Annotated, Any, ClassVar, cast

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.point_neuron_populations.pathway import PathwayConnectionProbability

ATOMIC_PATHWAY_CONNECTION_PROBABILITIES = PathwayConnectionProbability

AtomicPathwayConnectionProbabilityUnion = Annotated[
    ATOMIC_PATHWAY_CONNECTION_PROBABILITIES,
    Discriminator("type"),
]


class PathwayConnectionProbabilityReference(BlockReference):
    """A reference to a PathwayConnectionProbability block."""

    allowed_block_types: ClassVar[Any] = AtomicPathwayConnectionProbabilityUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(
            ATOMIC_PATHWAY_CONNECTION_PROBABILITIES
        )
    }

    @property
    def block(self) -> PathwayConnectionProbability:
        """The block associated with this reference."""
        if isinstance(super().block, PathwayConnectionProbability):
            return cast("PathwayConnectionProbability", super().block)
        msg = f"Expected block of type PathwayConnectionProbability, but got {type(super().block)}"
        raise TypeError(msg)

    @block.setter
    def block(self, value: PathwayConnectionProbability) -> None:
        BlockReference.block.fset(self, value)


PATHWAY_CONNECTION_PROBABILITY_REFERENCE_UNION = PathwayConnectionProbabilityReference
PATHWAY_CONNECTION_PROBABILITY_REFERENCE_TYPES = BlockReference.get_class_names(
    PATHWAY_CONNECTION_PROBABILITY_REFERENCE_UNION
)
