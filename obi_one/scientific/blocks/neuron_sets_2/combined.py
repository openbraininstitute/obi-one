import abc
import logging
import numpy as np
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

_MAX_COMBINED_DEPTH = 10

class SetOperation(StrEnum):
    UNION = "union"
    INTERSECT = "intersect"
    DIFF = "diff"

_OPERATION_MAP = {
    SetOperation.UNION: np.union1d,
    SetOperation.INTERSECT: np.intersect1d,
    SetOperation.DIFF: np.setdiff1d,
}

class CombinedBaseNeuronSet(NeuronSet, abc.ABC):
    """Abstract base class for combining neuron sets within and across node populations."""

    base_neuron_set: NeuronSet 
    combined_with: list[tuple[NeuronSet, SetOperation]]

    def check_combined_depth(
        self, visited: set[str] | None = None, depth: int = _MAX_COMBINED_DEPTH
    ) -> None:
        if not self.has_block_name():
            msg = "Block name must be set before checking combined depth."
            raise ValueError(msg)
        if visited is None:
            visited = set()
        if self.block_name in visited:
            msg = f"Recursive loop in combined neuron set '{self.block_name}'!"
            raise ValueError(msg)
        if depth == 0:
            msg = "Too many nested combined neuron sets!"
            raise ValueError(msg)
        visited.add(self.block_name)
        all_nsets = [self.base_neuron_set] + [nset for nset, _ in self.combined_with]
        for nset in all_nsets:
            if isinstance(nset, CombinedBaseNeuronSet):
                nset.check_combined_depth(visited, depth - 1)

    def get_populations(self, circuit: Circuit) -> list[str]:
        """Returns population names included in the neuron set."""
        all_pops = []
        all_nsets = [self.base_neuron_set] + [nset for nset, _ in self.combined_with]
        for nset in all_nsets:
            for pop in nset.get_populations(circuit):
                if pop not in all_pops:
                    all_pops.append(pop)
        return all_pops

    @staticmethod
    def _combine_ids(neuron_ids1: dict[str, list[int]], neuron_ids2: dict[str, list[int]], operation: SetOperation) -> dict[str, list[int]]:
        op_fct = _OPERATION_MAP[operation]
        npop_names = set(list(neuron_ids1) + list(neuron_ids2))
        combined = {}
        for npop in npop_names:
            comb_ids = op_fct(neuron_ids1.get(npop, []), neuron_ids2.get(npop, []))
            combined[npop] = list(comb_ids)
        return combined

    @staticmethod
    def _make_union_expression(circuit: Circuit, neuron_sets: list[NeuronSet]) -> tuple[dict | list, dict]:
        """Make union expression preserving symbolic notation, if possible"""
        expression = []
        combined = {}
        for nset in neuron_sets:
            nset_name = nset.block_name
            nset_def, nset_combined = nset.get_node_set_definition(circuit)
            combined.update(nset_combined)
            combined[nset_name] = nset_def
            expression.append(nset_name)
        return (expression, combined)

    def get_neuron_ids(self, circuit: Circuit) -> dict[str, list[int]]:
        """Returns list of neuron IDs per population."""
        self.check_combined_depth()
        comb_ids = self.base_neuron_set.get_neuron_ids(circuit)
        for nset, op in self.combined_with:
            with_ids = nset.get_neuron_ids(circuit)
            comb_ids = CombinedBaseNeuronSet._combine_ids(comb_ids, with_ids, op)
        return comb_ids

    def get_node_set_definition(
        self, circuit: Circuit, *, force_resolve_ids: bool = False
    ) -> tuple[dict | list, dict]:
        """Returns the SONATA node set definition, optionally forcing to resolve individual IDs.

        In case of a compound expression (list expression), any new definitions
        to be combined are returned as dict.
        """
        unions_only = all(op == SetOperation.UNION for _, op in self.combined_with)
        if force_resolve_ids or not unions_only:
            # Resolve and combine individual IDs per population and use in compound expression
            ids_per_npop = self.get_neuron_ids(circuit)
            expression, combined = NeuronSet.ids_to_node_set_definition(ids_per_npop, prefix=self.block_name, simplified=True)
        else:
            # Symbolic expression may be preserved
            self.check_combined_depth()
            all_nsets = [self.base_neuron_set] + [nset for nset, _ in self.combined_with]
            expression, combined = CombinedBaseNeuronSet._make_union_expression(circuit, all_nsets)
        return (expression, combined)


    # def _get_combined(self) -> list[str]:


    # def _get_expression(self, circuit: Circuit) -> dict | list:
    #     """Returns the SONATA node set expression."""
    #     self.check_combined_depth()
    #     return self._get_combined()


    # @staticmethod
    # def get_node_set_populations(node_set: str, circuit: Circuit) -> list[str]:
    #     """Returns a list of all node populations a node set resolves in."""
    #     node_populations = []
    #     for npop in circuit.sonata_circuit.nodes.population_names:
    #         try:
    #             node_ids = circuit.sonata_circuit.nodes[npop].ids(node_set)
    #         except snap.BluepySnapError:
    #             # In case of an error (e.g., "No such attribute"), return empty list
    #             node_ids = []
    #         if node_ids:
    #             node_populations.append(npop)
    #     return node_populations


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
