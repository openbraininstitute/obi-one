import logging

import numpy as np
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.synaptic_model_assigners.base import SynapseModelAssigner
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetReference

L = logging.getLogger(__name__)


class InterNeuronSetSynapticModelAssigner(SynapseModelAssigner):
    source_neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Source)",
        description="Source neuron set to simulate",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
            SchemaKey.SUPPORTS_VIRTUAL: True,
        },
    )

    targeted_neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Target neuron set to simulate",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
            SchemaKey.SUPPORTS_VIRTUAL: False,
        },
    )

    # This doesn't seem to be called from anywhere
    def validate_for_circuit(self, circuit: Circuit) -> None:
        circ = circuit.sonata_circuit
        ep = circ.edges[self.edge_population_name]
        specified_source = self.source_neuron_set.block.node_population  # ty:ignore[unresolved-attribute]
        specified_target = self.targeted_neuron_set.block.node_population  # ty:ignore[unresolved-attribute]
        if ep.source.name != specified_source:
            err_str = f"{ep.name} has source {ep.source.name} but {specified_source} is specified!"
            raise ValueError(err_str)
        if ep.target.name != specified_target:
            err_str = f"{ep.name} has source {ep.target.name} but {specified_target} is specified!"
            raise ValueError(err_str)

    def _edge_indices(self, circuit: Circuit) -> np.ndarray:
        circ = circuit.sonata_circuit
        ep = circ.edges[self.edge_population_name]
        src_ids = self.source_neuron_set.block.get_neuron_ids(circuit, population=ep.source.name)  # ty:ignore[unresolved-attribute]
        tgt_ids = self.targeted_neuron_set.block.get_neuron_ids(circuit, population=ep.target.name)  # ty:ignore[unresolved-attribute]
        return ep.pathway_edges(source=src_ids, target=tgt_ids)
