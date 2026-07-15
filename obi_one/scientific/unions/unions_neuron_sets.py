import abc
from typing import Annotated, Any, ClassVar, cast

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.neuron_sets.base import NeuronSet
from obi_one.scientific.blocks.neuron_sets.deprecated import (
    AllNeurons,
    ExcitatoryNeurons,
    IDNeuronSet,
    InhibitoryNeurons,
    PredefinedNeuronSet,
    nbS1POmInputs,
    nbS1VPMInputs,
    rCA1CA3Inputs,
)
from obi_one.scientific.blocks.neuron_sets.id import (
    BiophysicalPopulationIDNeuronSet,
    PointPopulationIDNeuronSet,
    VirtualPopulationIDNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.population import (
    BiophysicalPopulationNeuronSet,
    PointPopulationNeuronSet,
    VirtualPopulationNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.predefined import (
    BiophysicalPopulationPredefinedNeuronSet,
    PointPopulationPredefinedNeuronSet,
    VirtualPopulationPredefinedNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.property import (
    BiophysicalPopulationPropertyNeuronSet,
    PointPopulationPropertyNeuronSet,
    VirtualPopulationPropertyNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.specific import (
    AllBiophysicalNeurons,
    AllPointNeurons,
)

# Deprecated neuron sets predate the population-typed taxonomy: back then a neuron set carried no
# population type at all, so a config written before the rework uses any of them in either slot,
# regardless of the type the class nominally declares now -- AllNeurons (nominally biophysical)
# selects the virtual input population of an ME-model-with-synapses simulation, and
# PredefinedNeuronSet merely names a node set, which may resolve in a population of either type.
#
# They are deliberately NOT offered for point populations: point-neuron support was introduced by
# the same rework that deprecated them, so no pre-rework config can target a point population, and
# these blocks have no meaning for one.
#
# This only affects which stored configs still load: being deprecated, every one of them raises as
# soon as it is resolved against a circuit, so a config using one still has to be migrated before
# it can be run.
_DEPRECATED_NEURON_SETS = (
    AllNeurons
    | ExcitatoryNeurons
    | InhibitoryNeurons
    | IDNeuronSet
    | PredefinedNeuronSet
    | rCA1CA3Inputs
    | nbS1POmInputs
    | nbS1VPMInputs
)

_ALL_DEPRECATED_NEURON_SETS = _DEPRECATED_NEURON_SETS

ATOMIC_BIOPHYSICAL_NEURON_SETS = (
    BiophysicalPopulationPropertyNeuronSet
    | BiophysicalPopulationIDNeuronSet
    | BiophysicalPopulationNeuronSet
    | AllBiophysicalNeurons
    | BiophysicalPopulationPredefinedNeuronSet
    | _DEPRECATED_NEURON_SETS
)
ATOMIC_VIRTUAL_NEURON_SETS = (
    VirtualPopulationPropertyNeuronSet
    | VirtualPopulationIDNeuronSet
    | VirtualPopulationNeuronSet
    | VirtualPopulationPredefinedNeuronSet
    | _DEPRECATED_NEURON_SETS
)
ATOMIC_POINT_NEURON_SETS = (
    PointPopulationPropertyNeuronSet
    | PointPopulationIDNeuronSet
    | PointPopulationNeuronSet
    | AllPointNeurons
    | PointPopulationPredefinedNeuronSet
)

ATOMIC_ALL_NEURON_SETS = (
    ATOMIC_BIOPHYSICAL_NEURON_SETS | ATOMIC_VIRTUAL_NEURON_SETS | ATOMIC_POINT_NEURON_SETS
)

AtomicBiophysicalNeuronSetUnion = Annotated[
    ATOMIC_BIOPHYSICAL_NEURON_SETS,
    Discriminator("type"),
]

AtomicVirtualNeuronSetUnion = Annotated[
    ATOMIC_VIRTUAL_NEURON_SETS,
    Discriminator("type"),
]

AtomicPointNeuronSetUnion = Annotated[
    ATOMIC_POINT_NEURON_SETS,
    Discriminator("type"),
]

AtomicAllNeuronSetUnion = Annotated[
    ATOMIC_ALL_NEURON_SETS,
    Discriminator("type"),
]


class BaseNeuronSetReference(BlockReference, abc.ABC):
    @property
    def block(self) -> NeuronSet:
        """Returns the block associated with this reference."""
        if isinstance(super().block, NeuronSet):
            return cast("NeuronSet", super().block)
        msg = f"Expected block of type NeuronSet, but got {type(super().block)}"
        raise TypeError(msg)

    @block.setter
    def block(self, value: NeuronSet) -> None:
        BlockReference.block.fset(self, value)


class BiophysicalNeuronSetReference(BaseNeuronSetReference):
    """A reference to a Biophysical NeuronSet block."""

    allowed_block_types: ClassVar[Any] = AtomicBiophysicalNeuronSetUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(ATOMIC_BIOPHYSICAL_NEURON_SETS)
    }


class VirtualNeuronSetReference(BaseNeuronSetReference):
    """A reference to a Virtual NeuronSet2 block."""

    allowed_block_types: ClassVar[Any] = AtomicVirtualNeuronSetUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(ATOMIC_VIRTUAL_NEURON_SETS)
    }


class PointNeuronSetReference(BaseNeuronSetReference):
    """A reference to a Point NeuronSet2 block."""

    allowed_block_types: ClassVar[Any] = AtomicPointNeuronSetUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(ATOMIC_POINT_NEURON_SETS)
    }


_DEPRECATED_NEURON_SET_REFERENCE_MESSAGE = (
    "NeuronSetReference is deprecated. Use BiophysicalNeuronSetReference, "
    "VirtualNeuronSetReference, or PointNeuronSetReference instead."
)


class NeuronSetReference(BlockReference):
    """NeuronSetReference is Deprecated."""

    allowed_block_types: ClassVar[Any] = _ALL_DEPRECATED_NEURON_SETS

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_ALL_DEPRECATED_NEURON_SETS)
    }

    @property
    def block(self) -> NeuronSet:
        raise DeprecationWarning(_DEPRECATED_NEURON_SET_REFERENCE_MESSAGE)

    @block.setter
    def block(self, value: NeuronSet) -> None:  # noqa: ARG002, PLR6301
        # The setter is invoked while deserializing legacy configs (the model validator
        # `fill_block_references_and_names` assigns resolved blocks to references). Raising here
        # ensures that loading any config containing a deprecated NeuronSetReference fails with a
        # clear migration message instead of a confusing "has no setter" AttributeError.
        raise DeprecationWarning(_DEPRECATED_NEURON_SET_REFERENCE_MESSAGE)


ATOMIC_ALL_NEURON_SETS_REFERENCE_UNION = (
    BiophysicalNeuronSetReference
    | VirtualNeuronSetReference
    | PointNeuronSetReference
    | NeuronSetReference
)
ATOMIC_NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION = (
    BiophysicalNeuronSetReference | PointNeuronSetReference | NeuronSetReference
)
ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION = BiophysicalNeuronSetReference | NeuronSetReference
ATOMIC_VIRTUAL_NEURON_SETS_REFERENCE_UNION = VirtualNeuronSetReference | NeuronSetReference
# NeuronSetReference is intentionally excluded from the point union: it only references deprecated
# neuron sets, which are not offered for point populations (see above), so it must not be offered
# for a point-only reference field.
ATOMIC_POINT_NEURON_SETS_REFERENCE_UNION = PointNeuronSetReference

"""
Lists of reference types

Derived directly from the reference unions above so the two can never drift apart.
The `|` unions are already flattened and de-duplicated (`NeuronSetReference` is a member of
several of them but appears only once), and a bare (non-union) reference such as
`ATOMIC_POINT_NEURON_SETS_REFERENCE_UNION` yields a single-element list.
"""

ATOMIC_ALL_NEURON_SETS_REFERENCE_TYPES = BlockReference.get_class_names(
    ATOMIC_ALL_NEURON_SETS_REFERENCE_UNION
)
ATOMIC_NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES = BlockReference.get_class_names(
    ATOMIC_NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION
)
ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES = BlockReference.get_class_names(
    ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION
)
ATOMIC_VIRTUAL_NEURON_SETS_REFERENCE_TYPES = BlockReference.get_class_names(
    ATOMIC_VIRTUAL_NEURON_SETS_REFERENCE_UNION
)
ATOMIC_POINT_NEURON_SETS_REFERENCE_TYPES = BlockReference.get_class_names(
    ATOMIC_POINT_NEURON_SETS_REFERENCE_UNION
)
