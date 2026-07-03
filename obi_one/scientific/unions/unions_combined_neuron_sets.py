from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.neuron_sets.combined import (
    BiophysicalCombinedNeuronSet,
    PointCombinedNeuronSet,
    NonVirtualCombinedNeuronSet,
    VirtualCombinedNeuronSet,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    ATOMIC_ALL_NEURON_SETS,
    ATOMIC_ALL_NEURON_SETS_REFERENCE_TYPES,
    ATOMIC_ALL_NEURON_SETS_REFERENCE_UNION,
    ATOMIC_BIOPHYSICAL_NEURON_SETS,
    ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
    ATOMIC_VIRTUAL_NEURON_SETS,
    ATOMIC_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
    ATOMIC_POINT_NEURON_SETS,
    ATOMIC_POINT_NEURON_SETS_REFERENCE_TYPES,
    BaseNeuronSetReference,
)

_COMBINED_BIOPHYSICAL_NEURON_SETS = BiophysicalCombinedNeuronSet
_COMBINED_POINT_NEURON_SETS = PointCombinedNeuronSet
_COMBINED_VIRTUAL_NEURON_SETS = VirtualCombinedNeuronSet
_COMBINED_NON_VIRTUAL_NEURON_SETS = NonVirtualCombinedNeuronSet

CombinedBiophysicalNeuronSetUnion = Annotated[
    _COMBINED_BIOPHYSICAL_NEURON_SETS,
    Discriminator("type"),
]


_BIOPHYSICAL_NEURON_SETS = ATOMIC_BIOPHYSICAL_NEURON_SETS | _COMBINED_BIOPHYSICAL_NEURON_SETS
_POINT_NEURON_SETS = ATOMIC_POINT_NEURON_SETS | _COMBINED_POINT_NEURON_SETS
_VIRTUAL_NEURON_SETS = ATOMIC_VIRTUAL_NEURON_SETS | _COMBINED_VIRTUAL_NEURON_SETS
_NON_VIRTUAL_NEURON_SETS = _COMBINED_NON_VIRTUAL_NEURON_SETS
_ALL_NEURON_SETS = (
    ATOMIC_ALL_NEURON_SETS 
    | _BIOPHYSICAL_NEURON_SETS 
    | _POINT_NEURON_SETS
    | _VIRTUAL_NEURON_SETS
    | _NON_VIRTUAL_NEURON_SETS
)

AllNeuronSetUnion = Annotated[
    _ALL_NEURON_SETS,
    Discriminator("type"),
]

BiophysicalNeuronSetUnion = Annotated[
    _BIOPHYSICAL_NEURON_SETS,
    Discriminator("type"),
]

NEURONSimulationNeuronSetUnion = AllNeuronSetUnion

ALL_NEURON_SETS_REFERENCE_UNION = (ATOMIC_ALL_NEURON_SETS_REFERENCE_UNION,)


class CombinedAtomicBiophysicalNeuronSetReference(BaseNeuronSetReference):
    """A reference to a Combined Biophysical NeuronSet block."""

    allowed_block_types: ClassVar[Any] = CombinedBiophysicalNeuronSetUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_COMBINED_BIOPHYSICAL_NEURON_SETS)
    }


COMBINED_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES = [
    CombinedAtomicBiophysicalNeuronSetReference.__name__,
]

BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES = (
    ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES
    + COMBINED_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES
)

ALL_NEURON_SETS_REFERENCE_TYPES = (
    ATOMIC_ALL_NEURON_SETS_REFERENCE_TYPES + COMBINED_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES
)


# NEURONSimulationNeuronSetUnion = Annotated[
#     ATOMIC_ALL_NEURON_SETS,
#     Discriminator("type"),
# ]

# NEURONMEModelWithSynapsesNeuronSetUnion = Annotated[
#     ATOMIC_VIRTUAL_NEURON_SETS,
#     Discriminator("type"),
# ]

# Brian2SimulationNeuronSetUnion = AtomicPointNeuronSetUnion
# LearningEngineNeuronSetUnion = AtomicPointNeuronSetUnion
# CircuitExtractionNeuronSetUnion = Annotated[
#     ATOMIC_BIOPHYSICAL_NEURON_SETS | ATOMIC_POINT_NEURON_SETS,
#     Discriminator("type"),
# ]
# NEURONSynapseParameterizationNeuronSetUnion = NEURONSimulationNeuronSetUnion


def resolve_neuron_set_ref_to_node_set(
    neuron_set_reference: ALL_NEURON_SETS_REFERENCE_UNION | None, default_node_set: str
) -> str:
    if neuron_set_reference is None:
        return default_node_set

    return neuron_set_reference.block.block_name


def resolve_neuron_set_ref_to_neuron_set(
    neuron_set_reference: ALL_NEURON_SETS_REFERENCE_UNION | None,
    default_neuron_set_reference: ALL_NEURON_SETS_REFERENCE_UNION | None,
) -> AtomicAllNeuronSetUnion | None:
    if neuron_set_reference is None:
        if default_neuron_set_reference is None:
            msg = (
                "NeuronSet2Reference is None and no default_neuron_set provided. "
                "Cannot resolve to a NeuronSet."
            )
            raise ValueError(msg)

        return default_neuron_set_reference.block  # ty:ignore[invalid-return-type]

    return neuron_set_reference.block  # ty:ignore[invalid-return-type]
