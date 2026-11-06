from typing import Annotated, Any, ClassVar, cast

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.point_neuron_populations.pd14 import PD14PointNeuron
from obi_one.scientific.blocks.point_neuron_populations.population import PointNeuronPopulation

# The reference accepts both the plain and the preset population blocks, so a config using either
# resolves. The scan-config editor offers both as block-dictionary variants (see
# PointNeuronPopulationUnion below); PD14PointNeuron shows only its ``preset`` selector.
ATOMIC_POINT_NEURON_POPULATIONS = PointNeuronPopulation | PD14PointNeuron

AtomicPointNeuronPopulationUnion = Annotated[
    ATOMIC_POINT_NEURON_POPULATIONS,
    Discriminator("type"),
]


class PointNeuronPopulationReference(BlockReference):
    """A reference to a PointNeuronPopulation block."""

    allowed_block_types: ClassVar[Any] = AtomicPointNeuronPopulationUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(ATOMIC_POINT_NEURON_POPULATIONS)
    }

    @property
    def block(self) -> PointNeuronPopulation:
        """The block associated with this reference."""
        if isinstance(super().block, PointNeuronPopulation):
            return cast("PointNeuronPopulation", super().block)
        msg = f"Expected block of type PointNeuronPopulation, but got {type(super().block)}"
        raise TypeError(msg)

    @block.setter
    def block(self, value: PointNeuronPopulation) -> None:
        BlockReference.block.fset(self, value)


POINT_NEURON_POPULATION_REFERENCE_UNION = PointNeuronPopulationReference
POINT_NEURON_POPULATION_REFERENCE_TYPES = BlockReference.get_class_names(
    POINT_NEURON_POPULATION_REFERENCE_UNION
)

# Union of point-neuron population block types offered by the scan-config editor's block
# dictionary. Both the free-form PointNeuronPopulation and the preset-only PD14PointNeuron are
# offered; the latter shows only its ``preset`` selector (all other fields are ui_hidden).
PointNeuronPopulationUnion = AtomicPointNeuronPopulationUnion
