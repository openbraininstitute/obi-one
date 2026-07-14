import logging

import numpy as np
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.synaptic_model_assigners.base import SynapseModelAssigner
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.unions.unions_combined_neuron_sets import (
    ALL_NEURON_SETS_REFERENCE_UNION,
    ALL_NEURON_SETS_REFERENCE_TYPES,
)

L = logging.getLogger(__name__)


class PresynapticNeuronSetSynapticModelAssigner(SynapseModelAssigner):
    """Assign a synaptic model to the efferent synapses of a presynaptic neuron set."""

    source_neuron_set: ALL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Neuron Set (Source)",
        description="Source neuron set to simulate",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: ALL_NEURON_SETS_REFERENCE_TYPES,
            SchemaKey.PARAMETER_ORDER_PRIORITY: 100,
        },
    )

    # This doesn't seem to be called from anywhere
    def validate_for_circuit(self, circuit: Circuit) -> None:
        circ = circuit.sonata_circuit
        ep = circ.edges[self.edge_population_name]
        specified_source = self.source_neuron_set.block.node_population  # ty:ignore[unresolved-attribute]
        if ep.source.name != specified_source:
            err_str = f"{ep.name} has source {ep.source.name} but {specified_source} is specified!"
            raise ValueError(err_str)

    def _edge_indices(self, circuit: Circuit) -> np.ndarray:
        circ = circuit.sonata_circuit
        ep = circ.edges[self.edge_population_name]
        src_ids = self.source_neuron_set.block.get_neuron_ids(circuit)[ep.source.name]  # ty:ignore[unresolved-attribute]
        return ep.efferent_edges(src_ids)
