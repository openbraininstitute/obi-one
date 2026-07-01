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
    AllVirtualNeurons,
)

_DEPRECATED_BIOPHYSICAL_NEURON_SETS = (
    AllNeurons | ExcitatoryNeurons | InhibitoryNeurons | IDNeuronSet
)
_DEPRECATED_VIRTUAL_NEURON_SETS = rCA1CA3Inputs | nbS1POmInputs | nbS1VPMInputs
_ALL_DEPRECATED_NEURON_SETS = _DEPRECATED_BIOPHYSICAL_NEURON_SETS | _DEPRECATED_VIRTUAL_NEURON_SETS

_BIOPHYSICAL_NEURON_SETS = (
    BiophysicalPopulationPropertyNeuronSet
    | BiophysicalPopulationIDNeuronSet
    | BiophysicalPopulationNeuronSet
    | AllBiophysicalNeurons
    | BiophysicalPopulationPredefinedNeuronSet
    | _DEPRECATED_BIOPHYSICAL_NEURON_SETS
)
_VIRTUAL_NEURON_SETS = (
    VirtualPopulationPropertyNeuronSet
    | VirtualPopulationIDNeuronSet
    | VirtualPopulationNeuronSet
    | VirtualPopulationPredefinedNeuronSet
    | _DEPRECATED_VIRTUAL_NEURON_SETS
)
_POINT_NEURON_SETS = (
    PointPopulationPropertyNeuronSet
    | PointPopulationIDNeuronSet
    | PointPopulationNeuronSet
    | AllPointNeurons
    | PointPopulationPredefinedNeuronSet
)

_ALL_NEURON_SETS = _BIOPHYSICAL_NEURON_SETS | _VIRTUAL_NEURON_SETS | _POINT_NEURON_SETS

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

AllNeuronSetUnion = Annotated[
    _ALL_NEURON_SETS,
    Discriminator("type"),
]

NEURONSimulationNeuronSetUnion = Annotated[
    _ALL_NEURON_SETS,
    Discriminator("type"),
]

NEURONMEModelWithSynapsesNeuronSetUnion = Annotated[
    _VIRTUAL_NEURON_SETS,
    Discriminator("type"),
]

Brian2SimulationNeuronSetUnion = PointNeuronSetUnion
LearningEngineNeuronSetUnion = PointNeuronSetUnion
CircuitExtractionNeuronSetUnion = Annotated[
    _BIOPHYSICAL_NEURON_SETS | _POINT_NEURON_SETS,
    Discriminator("type"),
]
NEURONSynapseParameterizationNeuronSetUnion = NEURONSimulationNeuronSetUnion


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
    """A reference to a Biophysical or Point NeuronSet2 block."""

    allowed_block_types: ClassVar[Any] = BiophysicalNeuronSetUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_BIOPHYSICAL_NEURON_SETS)
    }


class VirtualNeuronSetReference(BaseNeuronSetReference):
    """A reference to a Virtual NeuronSet2 block."""

    allowed_block_types: ClassVar[Any] = VirtualNeuronSetUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_VIRTUAL_NEURON_SETS)
    }


class PointNeuronSetReference(BaseNeuronSetReference):
    """A reference to a Point NeuronSet2 block."""

    allowed_block_types: ClassVar[Any] = PointNeuronSetUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_POINT_NEURON_SETS)
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


ALL_NEURON_SETS_REFERENCE_UNION = (
    BiophysicalNeuronSetReference
    | VirtualNeuronSetReference
    | PointNeuronSetReference
    | NeuronSetReference
)
NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION = (
    BiophysicalNeuronSetReference | PointNeuronSetReference | NeuronSetReference
)
BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION = BiophysicalNeuronSetReference | NeuronSetReference
VIRTUAL_NEURON_SETS_REFERENCE_UNION = VirtualNeuronSetReference | NeuronSetReference
POINT_NEURON_SETS_REFERENCE_UNION = PointNeuronSetReference

ALL_NEURON_SETS_REFERENCE_TYPES = [
    BiophysicalNeuronSetReference.__name__,
    VirtualNeuronSetReference.__name__,
    PointNeuronSetReference.__name__,
    NeuronSetReference.__name__,
]
NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES = [
    BiophysicalNeuronSetReference.__name__,
    PointNeuronSetReference.__name__,
    NeuronSetReference.__name__,
]
BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES = [
    BiophysicalNeuronSetReference.__name__,
    NeuronSetReference.__name__,
]
VIRTUAL_NEURON_SETS_REFERENCE_TYPES = [
    VirtualNeuronSetReference.__name__,
    NeuronSetReference.__name__,
]
# NeuronSetReference is intentionally excluded: it only references deprecated biophysical/virtual
# neuron sets (never point sets), so it must not be offered for a point-only reference field. This
# keeps the list aligned with POINT_NEURON_SETS_REFERENCE_UNION above.
POINT_NEURON_SETS_REFERENCE_TYPES = [PointNeuronSetReference.__name__]


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
