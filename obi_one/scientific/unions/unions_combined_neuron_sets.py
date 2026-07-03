from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.neuron_sets.combined import (
    BiophysicalCombinedNeuronSet,
    NonVirtualCombinedNeuronSet,
    PointCombinedNeuronSet,
    VirtualCombinedNeuronSet,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    ATOMIC_ALL_NEURON_SETS,
    ATOMIC_ALL_NEURON_SETS_REFERENCE_TYPES,
    ATOMIC_ALL_NEURON_SETS_REFERENCE_UNION,
    ATOMIC_BIOPHYSICAL_NEURON_SETS,
    ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
    ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION,
    ATOMIC_POINT_NEURON_SETS,
    ATOMIC_POINT_NEURON_SETS_REFERENCE_TYPES,
    ATOMIC_POINT_NEURON_SETS_REFERENCE_UNION,
    ATOMIC_VIRTUAL_NEURON_SETS,
    ATOMIC_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
    ATOMIC_VIRTUAL_NEURON_SETS_REFERENCE_UNION,
    BaseNeuronSetReference,
)

_COMBINED_BIOPHYSICAL_NEURON_SETS = BiophysicalCombinedNeuronSet
_COMBINED_POINT_NEURON_SETS = PointCombinedNeuronSet
_COMBINED_VIRTUAL_NEURON_SETS = VirtualCombinedNeuronSet
_COMBINED_NON_VIRTUAL_NEURON_SETS = (
    BiophysicalCombinedNeuronSet | PointCombinedNeuronSet | NonVirtualCombinedNeuronSet
)

CombinedBiophysicalNeuronSetUnion = Annotated[
    _COMBINED_BIOPHYSICAL_NEURON_SETS,
    Discriminator("type"),
]

CombinedPointNeuronSetUnion = Annotated[
    _COMBINED_POINT_NEURON_SETS,
    Discriminator("type"),
]

CombinedVirtualNeuronSetUnion = Annotated[
    _COMBINED_VIRTUAL_NEURON_SETS,
    Discriminator("type"),
]

CombinedNonVirtualNeuronSetUnion = Annotated[
    _COMBINED_NON_VIRTUAL_NEURON_SETS,
    Discriminator("type"),
]


_BIOPHYSICAL_NEURON_SETS = ATOMIC_BIOPHYSICAL_NEURON_SETS | _COMBINED_BIOPHYSICAL_NEURON_SETS
_POINT_NEURON_SETS = ATOMIC_POINT_NEURON_SETS | _COMBINED_POINT_NEURON_SETS
_VIRTUAL_NEURON_SETS = ATOMIC_VIRTUAL_NEURON_SETS | _COMBINED_VIRTUAL_NEURON_SETS
_NON_VIRTUAL_NEURON_SETS = _COMBINED_NON_VIRTUAL_NEURON_SETS
_ALL_NEURON_SETS = (
    _BIOPHYSICAL_NEURON_SETS
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

VirtualNeuronSetUnion = Annotated[
    _VIRTUAL_NEURON_SETS,
    Discriminator("type"),
]

PointNeuronSetUnion = Annotated[
    _POINT_NEURON_SETS,
    Discriminator("type"),
]

NonVirtualNeuronSetUnion = Annotated[
    _NON_VIRTUAL_NEURON_SETS,
    Discriminator("type"),
]

NEURONSimulationNeuronSetUnion = AllNeuronSetUnion
CircuitExtractionNeuronSetUnion = NonVirtualNeuronSetUnion
NEURONMEModelWithSynapsesNeuronSetUnion = VirtualNeuronSetUnion
Brian2SimulationNeuronSetUnion = PointNeuronSetUnion
LearningEngineNeuronSetUnion = PointNeuronSetUnion
NEURONSynapseParameterizationNeuronSetUnion = AllNeuronSetUnion


class CombinedBiophysicalNeuronSetReference(BaseNeuronSetReference):
    """A reference to a Combined Biophysical NeuronSet block."""

    allowed_block_types: ClassVar[Any] = CombinedBiophysicalNeuronSetUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_COMBINED_BIOPHYSICAL_NEURON_SETS)
    }

class CombinedPointNeuronSetReference(BaseNeuronSetReference):
    """A reference to a Combined Point NeuronSet block."""

    allowed_block_types: ClassVar[Any] = CombinedPointNeuronSetUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_COMBINED_POINT_NEURON_SETS)
    }
class CombinedVirtualNeuronSetReference(BaseNeuronSetReference):
    """A reference to a Combined Virtual NeuronSet block."""

    allowed_block_types: ClassVar[Any] = CombinedVirtualNeuronSetUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_COMBINED_VIRTUAL_NEURON_SETS)
    }

class CombinedNonVirtualNeuronSetReference(BaseNeuronSetReference):
    """A reference to a Combined Non-Virtual NeuronSet block."""

    allowed_block_types: ClassVar[Any] = CombinedNonVirtualNeuronSetUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_COMBINED_NON_VIRTUAL_NEURON_SETS)
    }




BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION = (
    ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION | CombinedBiophysicalNeuronSetReference
)

VIRTUAL_NEURON_SETS_REFERENCE_UNION = (
    ATOMIC_VIRTUAL_NEURON_SETS_REFERENCE_UNION | CombinedVirtualNeuronSetReference
)
POINT_NEURON_SETS_REFERENCE_UNION = (
    ATOMIC_POINT_NEURON_SETS_REFERENCE_UNION | CombinedPointNeuronSetReference
)
NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION = (
    BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION | POINT_NEURON_SETS_REFERENCE_UNION | CombinedNonVirtualNeuronSetReference
)

ALL_NEURON_SETS_REFERENCE_UNION = (
    BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION | VIRTUAL_NEURON_SETS_REFERENCE_UNION | POINT_NEURON_SETS_REFERENCE_UNION | NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION
)

COMBINED_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES = [
    CombinedBiophysicalNeuronSetReference.__name__,
]

COMBINED_POINT_NEURON_SETS_REFERENCE_TYPES = [
    CombinedPointNeuronSetReference.__name__,
]

COMBINED_VIRTUAL_NEURON_SETS_REFERENCE_TYPES = [
    CombinedVirtualNeuronSetReference.__name__,
]

COMBINED_NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES = [
    CombinedNonVirtualNeuronSetReference.__name__,
]

ALL_NEURON_SETS_REFERENCE_TYPES = (
    ATOMIC_ALL_NEURON_SETS_REFERENCE_TYPES + COMBINED_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES
)

BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES = (
    ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES
    + COMBINED_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES
)

POINT_NEURON_SETS_REFERENCE_TYPES = (
    ATOMIC_POINT_NEURON_SETS_REFERENCE_TYPES + COMBINED_POINT_NEURON_SETS_REFERENCE_TYPES
)

VIRTUAL_NEURON_SETS_REFERENCE_TYPES = (
    ATOMIC_VIRTUAL_NEURON_SETS_REFERENCE_TYPES + COMBINED_VIRTUAL_NEURON_SETS_REFERENCE_TYPES
)

NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES = (
    BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES + POINT_NEURON_SETS_REFERENCE_TYPES + COMBINED_NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES
)


def resolve_neuron_set_ref_to_node_set(
    neuron_set_reference: ALL_NEURON_SETS_REFERENCE_UNION | None, default_node_set: str
) -> str:
    if neuron_set_reference is None:
        return default_node_set

    return neuron_set_reference.block.block_name


def resolve_neuron_set_ref_to_neuron_set(
    neuron_set_reference: ALL_NEURON_SETS_REFERENCE_UNION | None,
    default_neuron_set_reference: ALL_NEURON_SETS_REFERENCE_UNION | None,
) -> AllNeuronSetUnion | None:
    if neuron_set_reference is None:
        if default_neuron_set_reference is None:
            msg = (
                "NeuronSet2Reference is None and no default_neuron_set provided. "
                "Cannot resolve to a NeuronSet."
            )
            raise ValueError(msg)

        return default_neuron_set_reference.block  # ty:ignore[invalid-return-type]

    return neuron_set_reference.block  # ty:ignore[invalid-return-type]
