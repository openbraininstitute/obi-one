from pydantic import Field
from pandas import DataFrame

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.unions.unions_synaptic_models import (
    SynapticModelReference,
)
from obi_one.scientific.library.circuit import Circuit


class SynapseModelAssigner(Block):
    overwrite_if_exists: bool = Field(
        title="Overwrite",
        description="Overwrite if a parameterization exists already.",
        default=False,
    )

    random_seed: int = Field(
        default=1,
        title="Random seed",
        description="Seed for drawing random values from physiological parameter distributions.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    edge_population_name: str = Field(
        title="EdgePopulation name",
        description="Name of an EdgePopulation of the SONATA circuit that is to be parameterized"
    )

    synaptic_model: SynapticModelReference = Field(
        title="Synaptic Model",
        description="Synaptic model to assign to the synapses between the source and target"
        " neuron sets.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: SynapticModelReference.__name__,
        },
    )

    def validate(self, circuit: Circuit) -> None:
        raise NotImplementedError("This is implemented in derived classes!")

    def edge_indices(self, circuit: Circuit) -> DataFrame:
        raise NotImplementedError("This is implemented in derived classes!")
    
    def assign_parameters(self, circuit: Circuit, params: DataFrame) -> None:
        indices_df = self.edge_indices(circuit)
        param_model = self.synaptic_model.block
        new_params = param_model.sample(indices_df)
        params.update(new_params)
