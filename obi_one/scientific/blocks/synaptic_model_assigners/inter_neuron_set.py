import logging
from typing import ClassVar

import numpy as np
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.synaptic_model_assigners.base import SynapseModelAssigner
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    ALL_NEURON_SETS_REFERENCE_UNION,
    ALL_NEURON_SETS_REFERENCE_TYPES,
    NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
    NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION,
)

L = logging.getLogger(__name__)


class InterNeuronSetSynapticModelAssigner(SynapseModelAssigner):
    """Assign a synaptic model to synapses between a source and target neuron set."""

    title: ClassVar[str] = "Inter Neuron Set"

    source_neuron_set: ALL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Neuron Set (Source)",
        description="Source neuron set to simulate",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: ALL_NEURON_SETS_REFERENCE_TYPES,
            SchemaKey.REFERENCE_TAG: ReferenceTag.SYNAPSE_ASSIGNMENT_SOURCE,
            SchemaKey.PARAMETER_ORDER_PRIORITY: 100,
        },
    )

    targeted_neuron_set: NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Target neuron set to simulate",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
            SchemaKey.REFERENCE_TAG: ReferenceTag.SYNAPSE_ASSIGNMENT_TARGET,
            SchemaKey.PARAMETER_ORDER_PRIORITY: 99,
        },
    )

    def validate_for_circuit(self, circuit: Circuit) -> None:
        super().validate_for_circuit(circuit)
        ep = circuit.sonata_circuit.edges[self.edge_population_name]
        self._validate_neuron_set_spans(circuit, self.source_neuron_set, "source", ep.source.name)
        self._validate_neuron_set_spans(
            circuit, self.targeted_neuron_set, "target", ep.target.name
        )

    def _edge_indices(self, circuit: Circuit) -> np.ndarray:
        circ = circuit.sonata_circuit
        ep = circ.edges[self.edge_population_name]
        src_ids = self.source_neuron_set.block.get_neuron_ids(circuit)[ep.source.name]  # ty:ignore[unresolved-attribute]
        tgt_ids = self.targeted_neuron_set.block.get_neuron_ids(circuit)[ep.target.name]  # ty:ignore[unresolved-attribute]
        return ep.pathway_edges(source=src_ids, target=tgt_ids)
