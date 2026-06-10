import abc
import logging
from enum import StrEnum
from typing import ClassVar, Literal

import numpy as np
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.neuron_sets_2.base import NeuronSet, NeuronSetPopulationType
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
)
from obi_one.scientific.unions.unions_neuron_sets_2 import (
    ALL_NEURON_SETS_REFERENCE_TYPES,
    ALL_NEURON_SETS_REFERENCE_UNION,
    BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
    BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION,
    NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
    NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION,
    POINT_NEURON_SETS_REFERENCE_TYPES,
    POINT_NEURON_SETS_REFERENCE_UNION,
    VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
    VIRTUAL_NEURON_SETS_REFERENCE_UNION,
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
    combined_with: NeuronSet
    operation: Literal[SetOperation.UNION, SetOperation.INTERSECT, SetOperation.DIFF] = Field(
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION,
        },
        title="Operation",
        description="Set option for combining the IDs in the neuron sets.",
        default=SetOperation.UNION,
    )

    def _resolve_refs(self) -> tuple[NeuronSet, NeuronSet]:
        """Resolve neuron set references to actual NeuronSet objects."""
        if self.base_neuron_set is None or self.combined_with is None:
            msg = "Both neuron set references must be set for combining."
            raise ValueError(msg)
        base_nset = (
            self.base_neuron_set.block
            if hasattr(self.base_neuron_set, "block")
            else self.base_neuron_set
        )
        with_nset = (
            self.combined_with.block if hasattr(self.combined_with, "block") else self.combined_with
        )
        return base_nset, with_nset  # ty:ignore[invalid-return-type]

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
        base_nset, with_nset = self._resolve_refs()
        for nset in [base_nset, with_nset]:
            if isinstance(nset, CombinedBaseNeuronSet):
                nset.check_combined_depth(visited, depth - 1)

    def get_populations(self, circuit: Circuit) -> list[str]:
        """Returns population names included in the neuron set."""
        base_nset, with_nset = self._resolve_refs()
        all_pops = []
        for nset in [base_nset, with_nset]:
            for pop in nset.get_populations(circuit):
                if pop not in all_pops:
                    all_pops.append(pop)
        return all_pops

    @staticmethod
    def _combine_ids(
        neuron_ids1: dict[str, list[int]],
        neuron_ids2: dict[str, list[int]],
        operation: SetOperation,
    ) -> dict[str, list[int]]:
        op_fct = _OPERATION_MAP[operation]
        npop_names = set(list(neuron_ids1) + list(neuron_ids2))
        combined = {}
        for npop in npop_names:
            comb_ids = op_fct(neuron_ids1.get(npop, []), neuron_ids2.get(npop, []))
            combined[npop] = list(comb_ids)
        return combined

    @staticmethod
    def _make_union_expression(
        circuit: Circuit, neuron_sets: list[NeuronSet]
    ) -> tuple[dict | list, dict]:
        """Make union expression preserving symbolic notation, if possible."""
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
        base_nset, with_nset = self._resolve_refs()
        base_ids = base_nset.get_neuron_ids(circuit)
        with_ids = with_nset.get_neuron_ids(circuit)
        comb_ids = CombinedBaseNeuronSet._combine_ids(base_ids, with_ids, self.operation)
        return comb_ids

    def get_node_set_definition(
        self, circuit: Circuit, *, force_resolve_ids: bool = False
    ) -> tuple[dict | list, dict]:
        """Returns the SONATA node set definition, optionally forcing to resolve individual IDs.

        In case of a compound expression (list expression), any new definitions
        to be combined are returned as dict.
        """
        is_union = self.operation == SetOperation.UNION
        if force_resolve_ids or not is_union:
            # Resolve and combine individual IDs per population and use in compound expression
            ids_per_npop = self.get_neuron_ids(circuit)
            expression, combined = NeuronSet.ids_to_node_set_definition(
                ids_per_npop, prefix=self.block_name, simplified=True
            )
        else:
            # Symbolic expression may be preserved
            self.check_combined_depth()
            base_nset, with_nset = self._resolve_refs()
            expression, combined = CombinedBaseNeuronSet._make_union_expression(
                circuit, [base_nset, with_nset]
            )
        return (expression, combined)


class CombinedNeuronSet(CombinedBaseNeuronSet):
    """Combine neuron sets of any type."""

    title: ClassVar[str] = "Combined (Any)"
    description: ClassVar[str] = "Use neuron sets of any type combined with set operations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.ANY

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no populations.",
        },
    }

    base_neuron_set: ALL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="First Neuron Set",
        description="Base neuron set to be combined.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: ALL_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    combined_with: ALL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Second Neuron Set",
        description="Neuron set to combine with.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: ALL_NEURON_SETS_REFERENCE_TYPES,
        },
    )


class BiophysicalCombinedNeuronSet(CombinedBaseNeuronSet):
    """Combine biophysical neuron sets."""

    title: ClassVar[str] = "Combined (Biophysical)"
    description: ClassVar[str] = "Use biophysical neuron sets combined with set operations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = (
        NeuronSetPopulationType.BIOPHYSICAL
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_BIOPHYSICAL_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no biophysical populations.",
        },
    }

    base_neuron_set: BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="First Neuron Set",
        description="Base neuron set to be combined.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    combined_with: BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Second Neuron Set",
        description="Neuron set to combine with.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )


class VirtualCombinedNeuronSet(CombinedBaseNeuronSet):
    """Combine virtual neuron sets."""

    title: ClassVar[str] = "Combined (Virtual)"
    description: ClassVar[str] = "Use virtual neuron sets combined with set operations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.VIRTUAL

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_VIRTUAL_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no virtual populations.",
        },
    }

    base_neuron_set: VIRTUAL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="First Neuron Set",
        description="Base neuron set to be combined.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    combined_with: VIRTUAL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Second Neuron Set",
        description="Neuron set to combine with.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )


class NonVirtualCombinedNeuronSet(CombinedBaseNeuronSet):
    """Combine non-virtual neuron sets."""

    title: ClassVar[str] = "Combined (Non-Virtual)"
    description: ClassVar[str] = "Use non-virtual neuron sets combined with set operations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = (
        NeuronSetPopulationType.NONVIRTUAL
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_NONVIRTUAL_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no non-virtual populations.",
        },
    }

    base_neuron_set: NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="First Neuron Set",
        description="Base neuron set to be combined.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    combined_with: NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Second Neuron Set",
        description="Neuron set to combine with.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )


class PointCombinedNeuronSet(CombinedBaseNeuronSet):
    """Combine point neuron sets."""

    title: ClassVar[str] = "Combined (Point)"
    description: ClassVar[str] = "Use point neuron sets combined with set operations."

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.POINT

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_POINT_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no point neuron populations.",
        },
    }

    base_neuron_set: POINT_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="First Neuron Set",
        description="Base neuron set to be combined.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: POINT_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    combined_with: POINT_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Second Neuron Set",
        description="Neuron set to combine with.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: POINT_NEURON_SETS_REFERENCE_TYPES,
        },
    )
