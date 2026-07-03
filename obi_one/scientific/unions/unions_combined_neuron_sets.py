from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.neuron_sets.combined import BiophysicalCombinedNeuronSet
from obi_one.scientific.unions.unions_neuron_sets import (
    _ALL_NEURON_SETS,
    _BIOPHYSICAL_NEURON_SETS,
    ALL_NEURON_SETS_REFERENCE_TYPES,
    BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
    BaseNeuronSetReference,
)

_COMBINED_BIOPHYSICAL_NEURON_SETS = BiophysicalCombinedNeuronSet

CombinedBiophysicalNeuronSetUnion = Annotated[
    _COMBINED_BIOPHYSICAL_NEURON_SETS,
    Discriminator("type"),
]


_SPECIAL_BIOPHYSICAL_NEURON_SETS = _BIOPHYSICAL_NEURON_SETS | _COMBINED_BIOPHYSICAL_NEURON_SETS
_SPECIAL_ALL_NEURON_SETS = _ALL_NEURON_SETS | _SPECIAL_BIOPHYSICAL_NEURON_SETS

SpecialAllNeuronSetUnion = Annotated[
    _SPECIAL_ALL_NEURON_SETS,
    Discriminator("type"),
]

SpecialBiophysicalNeuronSetUnion = Annotated[
    _SPECIAL_BIOPHYSICAL_NEURON_SETS,
    Discriminator("type"),
]

SpecialNEURONSimulationNeuronSetUnion = SpecialAllNeuronSetUnion


class CombinedBiophysicalNeuronSetReference(BaseNeuronSetReference):
    """A reference to a Combined Biophysical NeuronSet block."""

    allowed_block_types: ClassVar[Any] = CombinedBiophysicalNeuronSetUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_COMBINED_BIOPHYSICAL_NEURON_SETS)
    }


COMBINED_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES = [
    CombinedBiophysicalNeuronSetReference.__name__,
]

SPECIAL_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES = (
    BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES + COMBINED_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES
)

SPECIAL_ALL_NEURON_SETS_REFERENCE_TYPES = (
    ALL_NEURON_SETS_REFERENCE_TYPES + COMBINED_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES
)
