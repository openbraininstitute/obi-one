import abc
import logging
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.tuple import NamedTuple
from obi_one.scientific.blocks.neuron_sets_2.population import (
    BiophysicalPopulationNeuronSet,
    PointPopulationNeuronSet,
    PopulationNeuronSet,
    VirtualPopulationNeuronSet,
)
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.unions.unions_neuron_sets_2 import (
    BiophysicalNeuronSetReference,
    VirtualNeuronSetReference,
    PointNeuronSetReference,
)

L = logging.getLogger("obi-one")


# class CombinedNeuronSet(PopulationNeuronSet, abc.ABC):
#     """Neuron set definition by providing a list of neuron IDs."""
    

# class BiophysicalCombinedNeuronSet(CombinedNeuronSet, BiophysicalPopulationNeuronSet):
#     """Only biophysical neuron node populations are selectable."""

#     title: ClassVar[str] = "Combined (Biophysical)"

#     neuron_sets: BiophysicalCombinedNeuronSetNamedTuple = Field(
#         title="Neuron Sets to Combine",
#         description="List of neuron IDs to include in the neuron set.",
#         json_schema_extra={
#             SchemaKey.UI_ELEMENT: UIElement.NEURON_SET_COMBINATION,
#             SchemaKey.REFERENCE_TYPES: [BiophysicalNeuronSetReference.__name__],
#         },
#     )


# class VirtualCombinedNeuronSet(CombinedNeuronSet, VirtualPopulationNeuronSet):
#     """Only virtual neuron node populations are selectable."""

#     title: ClassVar[str] = "Combined (Virtual)"

#     neuron_sets: VirtualCombinedNeuronSetNamedTuple = Field(
#         title="Neuron Sets to Combine",
#         description="...",
#         json_schema_extra={
#             SchemaKey.UI_ELEMENT: UIElement.NEURON_SET_COMBINATION,
#             SchemaKey.REFERENCE_TYPES: [VirtualNeuronSetReference.__name__],
#         },
#     )


# class PointCombinedNeuronSet(CombinedNeuronSet, PointPopulationNeuronSet):
#     """Only point neuron node populations are selectable."""

#     title: ClassVar[str] = "Combined (Point)"

#     neuron_sets: PointCombinedNeuronSetNamedTuple = Field(
#         title="Neuron Sets to Combine",
#         description="...",
#         json_schema_extra={
#             SchemaKey.UI_ELEMENT: UIElement.NEURON_SET_COMBINATION,
#             SchemaKey.REFERENCE_TYPES: [PointNeuronSetReference.__name__],
#         },
#     )
