from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.neuron_sets.combined import (
    BiophysicalCombinedNeuronSet,
    NonVirtualCombinedNeuronSet,
    PointCombinedNeuronSet,
    VirtualCombinedNeuronSet,
)
from obi_one.scientific.unions_and_references.neuron_sets import (
    ATOMIC_BIOPHYSICAL_NEURON_SETS,
    ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION,
    ATOMIC_POINT_NEURON_SETS,
    ATOMIC_POINT_NEURON_SETS_REFERENCE_UNION,
    ATOMIC_VIRTUAL_NEURON_SETS,
    ATOMIC_VIRTUAL_NEURON_SETS_REFERENCE_UNION,
    BaseNeuronSetReference,
)

"""
Useful private unions
"""

_BIOPHYSICAL_NEURON_SETS = ATOMIC_BIOPHYSICAL_NEURON_SETS | BiophysicalCombinedNeuronSet
_POINT_NEURON_SETS = ATOMIC_POINT_NEURON_SETS | PointCombinedNeuronSet
_VIRTUAL_NEURON_SETS = ATOMIC_VIRTUAL_NEURON_SETS | VirtualCombinedNeuronSet
_NON_VIRTUAL_NEURON_SETS = (
    _BIOPHYSICAL_NEURON_SETS | _POINT_NEURON_SETS | NonVirtualCombinedNeuronSet
)
_ALL_NEURON_SETS = (
    _BIOPHYSICAL_NEURON_SETS | _POINT_NEURON_SETS | _VIRTUAL_NEURON_SETS | _NON_VIRTUAL_NEURON_SETS
)

"""
Annotated private unions
"""

_AllNeuronSetUnion = Annotated[
    _ALL_NEURON_SETS,
    Discriminator("type"),
]

_VirtualNeuronSetUnion = Annotated[
    _VIRTUAL_NEURON_SETS,
    Discriminator("type"),
]

_PointNeuronSetUnion = Annotated[
    _POINT_NEURON_SETS,
    Discriminator("type"),
]

_NonVirtualNeuronSetUnion = Annotated[
    _NON_VIRTUAL_NEURON_SETS,
    Discriminator("type"),
]

"""
Annotated public unions
"""

NEURONSimulationNeuronSetUnion = _AllNeuronSetUnion
CircuitExtractionNeuronSetUnion = _NonVirtualNeuronSetUnion
NEURONMEModelWithSynapsesNeuronSetUnion = _VirtualNeuronSetUnion
Brian2SimulationNeuronSetUnion = _PointNeuronSetUnion
LearningEngineNeuronSetUnion = _PointNeuronSetUnion
NEURONSynapseParameterizationNeuronSetUnion = _AllNeuronSetUnion


"""
Reference classes
"""


class CombinedBiophysicalNeuronSetReference(BaseNeuronSetReference):
    """A reference to a Combined Biophysical NeuronSet block."""

    allowed_block_types: ClassVar[Any] = Annotated[
        BiophysicalCombinedNeuronSet,
        Discriminator("type"),
    ]

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(BiophysicalCombinedNeuronSet)
    }


class CombinedPointNeuronSetReference(BaseNeuronSetReference):
    """A reference to a Combined Point NeuronSet block."""

    allowed_block_types: ClassVar[Any] = Annotated[
        PointCombinedNeuronSet,
        Discriminator("type"),
    ]

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(PointCombinedNeuronSet)
    }


class CombinedVirtualNeuronSetReference(BaseNeuronSetReference):
    """A reference to a Combined Virtual NeuronSet block."""

    allowed_block_types: ClassVar[Any] = Annotated[
        VirtualCombinedNeuronSet,
        Discriminator("type"),
    ]

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(VirtualCombinedNeuronSet)
    }


class CombinedNonVirtualNeuronSetReference(BaseNeuronSetReference):
    """A reference to a Combined Non-Virtual NeuronSet block."""

    allowed_block_types: ClassVar[Any] = Annotated[
        NonVirtualCombinedNeuronSet,
        Discriminator("type"),
    ]

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(NonVirtualCombinedNeuronSet)
    }


"""
Reference unions
"""

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
    BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION
    | POINT_NEURON_SETS_REFERENCE_UNION
    | CombinedNonVirtualNeuronSetReference
)

ALL_NEURON_SETS_REFERENCE_UNION = (
    BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION
    | VIRTUAL_NEURON_SETS_REFERENCE_UNION
    | POINT_NEURON_SETS_REFERENCE_UNION
    | NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION
)


"""
Lists of reference types

Derived directly from the reference unions above so the two can never drift apart.
The `|` unions are already flattened and de-duplicated (e.g. the deprecated
`NeuronSetReference`, which is a member of several atomic unions, appears only once),
so `get_class_names` simply reads off the member class names.
"""

BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES = BlockReference.get_class_names(
    BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION
)

POINT_NEURON_SETS_REFERENCE_TYPES = BlockReference.get_class_names(
    POINT_NEURON_SETS_REFERENCE_UNION
)

VIRTUAL_NEURON_SETS_REFERENCE_TYPES = BlockReference.get_class_names(
    VIRTUAL_NEURON_SETS_REFERENCE_UNION
)

NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES = BlockReference.get_class_names(
    NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION
)

ALL_NEURON_SETS_REFERENCE_TYPES = BlockReference.get_class_names(ALL_NEURON_SETS_REFERENCE_UNION)

"""
Resolve functions
"""


def resolve_neuron_set_ref_to_node_set(
    neuron_set_reference: ALL_NEURON_SETS_REFERENCE_UNION | None, default_node_set: str
) -> str:
    if neuron_set_reference is None:
        return default_node_set

    return neuron_set_reference.block.block_name


def resolve_neuron_set_ref_to_neuron_set(
    neuron_set_reference: ALL_NEURON_SETS_REFERENCE_UNION | None,
    default_neuron_set_reference: ALL_NEURON_SETS_REFERENCE_UNION | None,
) -> _AllNeuronSetUnion | None:
    if neuron_set_reference is None:
        if default_neuron_set_reference is None:
            msg = (
                "NeuronSet2Reference is None and no default_neuron_set provided. "
                "Cannot resolve to a NeuronSet."
            )
            raise ValueError(msg)

        return default_neuron_set_reference.block  # ty:ignore[invalid-return-type]

    return neuron_set_reference.block  # ty:ignore[invalid-return-type]
