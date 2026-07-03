import abc
import logging
from enum import StrEnum
from typing import ClassVar, Literal

import numpy as np
from pydantic import Field

from obi_one.core.block_reference import BlockReference
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.neuron_sets.base import NeuronSet, NeuronSetPopulationType
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    ATOMIC_ALL_NEURON_SETS_REFERENCE_TYPES,
    ATOMIC_ALL_NEURON_SETS_REFERENCE_UNION,
    ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
    ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION,
    ATOMIC_NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
    ATOMIC_NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION,
    ATOMIC_POINT_NEURON_SETS_REFERENCE_TYPES,
    ATOMIC_POINT_NEURON_SETS_REFERENCE_UNION,
    ATOMIC_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
    ATOMIC_VIRTUAL_NEURON_SETS_REFERENCE_UNION,
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

    base_neuron_set: BlockReference | None
    combined_with: list[
        tuple[
            BlockReference,
            Literal[SetOperation.UNION, SetOperation.INTERSECT, SetOperation.DIFF],
        ]
    ]

    def _resolve_refs(self) -> tuple[NeuronSet, list[tuple[NeuronSet, SetOperation]]]:
        """Resolve neuron set references to actual NeuronSet objects."""
        if self.base_neuron_set is None:
            msg = "Base neuron set reference must be set for combining."
            raise ValueError(msg)
        base_nset = (
            self.base_neuron_set.block
            if hasattr(self.base_neuron_set, "block")
            else self.base_neuron_set
        )
        combined_with = []
        for nset, op in self.combined_with:
            with_nset = nset.block if hasattr(nset, "block") else nset
            combined_with.append((with_nset, op))
        return base_nset, combined_with  # ty: ignore[invalid-return-type]

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
        base_nset, comb_with = self._resolve_refs()
        all_nsets = [base_nset] + [nset for nset, _ in comb_with]
        for nset in all_nsets:
            if isinstance(nset, CombinedBaseNeuronSet):
                nset.check_combined_depth(visited, depth - 1)

    def get_populations(self, circuit: Circuit) -> list[str]:
        """Returns population names included in the neuron set."""
        self.check_combined_depth()
        base_nset, comb_with = self._resolve_refs()
        all_nsets = [base_nset] + [nset for nset, _ in comb_with]
        all_pops = []
        for nset in all_nsets:
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
            combined[npop] = comb_ids.tolist()
        return combined

    @staticmethod
    def _make_union_expression(
        circuit: Circuit,
        neuron_sets: list[NeuronSet],
        prefix: str = "",
    ) -> tuple[dict | list, dict]:
        """Make union expression preserving symbolic notation, if possible."""
        expression = []
        combined = {}
        for nset in neuron_sets:
            nset_name = prefix + nset.block_name
            nset_def, nset_combined = nset.get_node_set_definition(circuit)
            combined.update(nset_combined)
            combined[nset_name] = nset_def
            expression.append(nset_name)
        return (expression, combined)

    def get_neuron_ids(self, circuit: Circuit) -> dict[str, list[int]]:
        """Returns list of neuron IDs per population."""
        self.check_combined_depth()
        self.check_populations_in_circuit(circuit=circuit)
        base_nset, comb_with = self._resolve_refs()
        comb_ids = base_nset.get_neuron_ids(circuit)
        for nset, op in comb_with:
            with_ids = nset.get_neuron_ids(circuit)
            comb_ids = CombinedBaseNeuronSet._combine_ids(comb_ids, with_ids, op)

        if all(len(ids) == 0 for ids in comb_ids.values()):
            L.warning("Combined neuron set empty!")

        return comb_ids

    def get_node_set_definition(
        self, circuit: Circuit, *, force_resolve_ids: bool = False
    ) -> tuple[dict | list, dict]:
        """Returns the SONATA node set definition, optionally forcing to resolve individual IDs.

        Returns a tuple of (expression, combined) where:

        - expression (dict): A single SONATA node set expression. Examples:
            - Symbolic by population: {"population": "pop_name"}
            - Symbolic by properties: {"layer": "6", "synapse_class": "EXC"}
            - Resolved IDs: {"population": "pop_name", "node_id": [1, 2, 3]}

        - expression (list): A compound expression referencing multiple named node sets.
            Example: ["__ClassName__blockname__0__", "__ClassName__blockname__1__"]
            Each name must exist as a key in the combined dict.
            Also used for symbolic references to existing node sets: ["Layer6"]

        - combined (dict): Additional node set definitions needed by a compound expression.
            Example: {"__ClassName__blockname__0__": {"population": "A", "node_id": [...]},
                      "__ClassName__blockname__1__": {"population": "B", "node_id": [...]}}
            Empty ({}) when expression is a single dict.

        Args:
            circuit: The circuit to resolve the node set in.
            force_resolve_ids: If True, always resolve to explicit neuron IDs
                instead of preserving symbolic expressions.
        """
        if not self.has_block_name():
            msg = "Block name must be set."
            raise ValueError(msg)
        unions_only = all(op == SetOperation.UNION for _, op in self.combined_with)
        if force_resolve_ids or not unions_only:
            # Resolve and combine individual IDs per population and use in compound expression
            ids_per_npop = self.get_neuron_ids(circuit)
            prefix = f"__{self.__class__.__name__}__{self.block_name}"
            expression, combined = NeuronSet.ids_to_node_set_definition(
                ids_per_npop, prefix=prefix, simplified=True
            )
        else:
            # Symbolic expression may be preserved
            self.check_combined_depth()
            self.check_populations_in_circuit(circuit=circuit)
            base_nset, comb_with = self._resolve_refs()
            all_nsets = [base_nset] + [nset for nset, _ in comb_with]
            prefix = f"__{self.__class__.__name__}__"
            expression, combined = CombinedBaseNeuronSet._make_union_expression(
                circuit, all_nsets, prefix
            )
        return (expression, combined)


class CombinedNeuronSet(CombinedBaseNeuronSet):
    """Combine neuron sets of any type."""

    title: ClassVar[str] = "Combined (Any)"
    description: ClassVar[str] = (
        "Use neuron sets of any type combined with set operations."
        " Operations will be applied from top to bottom."
    )

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.ANY

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no populations.",
        },
    }

    base_neuron_set: ATOMIC_ALL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Neuron Set",
        description="Base neuron set to be combined.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: ATOMIC_ALL_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    combined_with: list[
        tuple[
            ATOMIC_ALL_NEURON_SETS_REFERENCE_UNION,
            Literal[SetOperation.UNION, SetOperation.INTERSECT, SetOperation.DIFF],
        ]
    ] = Field(
        default_factory=list,
        title="Combine With",
        description="Neuron sets and set operations to combine with the base neuron set.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.NEURON_SET_COMBINATION,
            SchemaKey.REFERENCE_TYPES: ATOMIC_ALL_NEURON_SETS_REFERENCE_TYPES,
        },
    )


class BiophysicalCombinedNeuronSet(CombinedBaseNeuronSet):
    """Combine biophysical neuron sets."""

    title: ClassVar[str] = "Combined (Biophysical)"
    description: ClassVar[str] = (
        "Use biophysical neuron sets combined with set operations."
        " Operations will be applied from top to bottom."
    )

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

    base_neuron_set: ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Neuron Set",
        description="Base neuron set to be combined.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    combined_with: list[
        tuple[
            ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION,
            Literal[SetOperation.UNION, SetOperation.INTERSECT, SetOperation.DIFF],
        ]
    ] = Field(
        default_factory=list,
        title="Combine With",
        description="Neuron sets and set operations to combine with the base neuron set.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.NEURON_SET_COMBINATION,
            SchemaKey.REFERENCE_TYPES: ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )


class VirtualCombinedNeuronSet(CombinedBaseNeuronSet):
    """Combine virtual neuron sets."""

    title: ClassVar[str] = "Combined (Virtual)"
    description: ClassVar[str] = (
        "Use virtual neuron sets combined with set operations."
        " Operations will be applied from top to bottom."
    )

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.VIRTUAL

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_VIRTUAL_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no virtual populations.",
        },
    }

    base_neuron_set: ATOMIC_VIRTUAL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Neuron Set",
        description="Base neuron set to be combined.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: ATOMIC_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    combined_with: list[
        tuple[
            ATOMIC_VIRTUAL_NEURON_SETS_REFERENCE_UNION,
            Literal[SetOperation.UNION, SetOperation.INTERSECT, SetOperation.DIFF],
        ]
    ] = Field(
        default_factory=list,
        title="Combine With",
        description="Neuron sets and set operations to combine with the base neuron set.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.NEURON_SET_COMBINATION,
            SchemaKey.REFERENCE_TYPES: ATOMIC_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )


class NonVirtualCombinedNeuronSet(CombinedBaseNeuronSet):
    """Combine non-virtual neuron sets."""

    title: ClassVar[str] = "Combined (Non-Virtual)"
    description: ClassVar[str] = (
        "Use non-virtual neuron sets combined with set operations."
        " Operations will be applied from top to bottom."
    )

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

    base_neuron_set: ATOMIC_NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Neuron Set",
        description="Base neuron set to be combined.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: ATOMIC_NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    combined_with: list[
        tuple[
            ATOMIC_NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION,
            Literal[SetOperation.UNION, SetOperation.INTERSECT, SetOperation.DIFF],
        ]
    ] = Field(
        default_factory=list,
        title="Combine With",
        description="Neuron sets and set operations to combine with the base neuron set.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.NEURON_SET_COMBINATION,
            SchemaKey.REFERENCE_TYPES: ATOMIC_NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )


class PointCombinedNeuronSet(CombinedBaseNeuronSet):
    """Combine point neuron sets."""

    title: ClassVar[str] = "Combined (Point)"
    description: ClassVar[str] = (
        "Use point neuron sets combined with set operations."
        " Operations will be applied from top to bottom."
    )

    _neuron_set_population_type: ClassVar[NeuronSetPopulationType] = NeuronSetPopulationType.POINT

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_POINT_NEURON_SETS,
            SchemaKey.FALSE_MESSAGE: "This circuit has no point neuron populations.",
        },
    }

    base_neuron_set: ATOMIC_POINT_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Neuron Set",
        description="Base neuron set to be combined.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: ATOMIC_POINT_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    combined_with: list[
        tuple[
            ATOMIC_POINT_NEURON_SETS_REFERENCE_UNION,
            Literal[SetOperation.UNION, SetOperation.INTERSECT, SetOperation.DIFF],
        ]
    ] = Field(
        default_factory=list,
        title="Combine With",
        description="Neuron sets and set operations to combine with the base neuron set.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.NEURON_SET_COMBINATION,
            SchemaKey.REFERENCE_TYPES: ATOMIC_POINT_NEURON_SETS_REFERENCE_TYPES,
        },
    )
