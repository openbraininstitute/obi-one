import numpy as np
from pandas import DataFrame
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.unions_and_references.synaptic_models import (
    SynapticModelReference,
)


class SynapseModelAssigner(Block):
    overwrite_if_exists: bool = Field(
        title="Overwrite",
        description="Overwrite if a parameterization exists already.",
        default=False,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    random_seed: int | list[int] = Field(
        default=1,
        title="Random seed",
        description="Seed for drawing random values from physiological parameter distributions.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    edge_population_name: str = Field(
        title="EdgePopulation name",
        description="Name of an EdgePopulation of the SONATA circuit that is to be parameterized",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
        },
    )

    synaptic_model: SynapticModelReference | None = Field(
        default=None,
        title="Synaptic Model",
        description="Synaptic model to assign to the synapses between the source and target"
        " neuron sets.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [SynapticModelReference.__name__],
        },
    )

    # This doesn't seem to be called from anywhere
    def validate_for_circuit(self, circuit: Circuit) -> None:
        msg = (
            "Concrete subclasses of SynapseModelAssigner MUST implement "
            "the .validate_for_circuit() method."
        )
        raise NotImplementedError(msg)

    def _edge_indices(self, circuit: Circuit) -> np.ndarray:
        msg = (
            "Concrete subclasses of SynapseModelAssigner MUST implement the ._edge_indices() "
            "method to return the edge indices to which the synaptic model should be assigned."
        )
        raise NotImplementedError(msg)

    def edge_indices(
        self, circuit: Circuit, min_edge_id: int | None = None, max_edge_id: int | None = None
    ) -> DataFrame:
        circ = circuit.sonata_circuit
        ep = circ.edges[self.edge_population_name]
        indices = self._edge_indices(circuit)
        if min_edge_id is not None:
            indices = indices[indices >= min_edge_id]
        if max_edge_id is not None:
            indices = indices[indices < max_edge_id]
        return ep.get(indices, properties=["@source_node", "@target_node"])

    def create_parameters(
        self, circuit: Circuit, min_edge_id: int | None = None, max_edge_id: int | None = None
    ) -> DataFrame:
        indices_df = self.edge_indices(circuit, min_edge_id=min_edge_id, max_edge_id=max_edge_id)
        param_model = self.synaptic_model.block  # ty:ignore[unresolved-attribute]
        new_params = param_model.sample(indices_df)
        return new_params

    def assign_parameters(
        self,
        circuit: Circuit,
        params: DataFrame,
        min_edge_id: int | None = None,
        max_edge_id: int | None = None,
    ) -> None:
        new_params = self.create_parameters(
            circuit, min_edge_id=min_edge_id, max_edge_id=max_edge_id
        )
        params.update(new_params)
