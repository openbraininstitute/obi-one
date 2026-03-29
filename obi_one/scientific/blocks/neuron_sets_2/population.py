"""
PopulationNeuronSet(NeuronSet) [NEW] 
- node_population 
- sample_percentage 
- sample_seed 
- _population_type 

- Allows a user to select a whole node population, i.e., restricted to a single node population 
- Supports sub-sampling 
- Is aware of the population type (i.e., biophysical, point, virtual) 
- Can be used for either biophysical, point, or virtual populations 
- Replaces: AllNeurons, nbS1VPMInputs, nbS1POmInputs, rCA1CA3Inputs, etc. 
"""


import abc

class PopulationNeuronSet(NeuronSet, abc.ABC):
    """"""

    sample_percentage: (
        Annotated[NonNegativeFloat, Field(le=100)]
        | Annotated[list[Annotated[NonNegativeFloat, Field(le=100)]], Field(min_length=1)]
    ) = Field(
        default=100.0,
        title="Sample (Percentage)",
        description="Percentage of neurons to sample between 0 and 100%",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.PERCENT,
        },
    )

    sample_seed: int | list[int] = Field(
        default=1,
        title="Sample Seed",
        description="Seed for random sampling.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

class BiophysicalPopulationNeuronSet(PopulationNeuronSet):
    """Only biophysical node populations are selectable."""

    population: str = Field(
        default="",
        title="Population",
        description="Name of the biophysical node population to select from.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.NODE_POPULATION_DROPDOWN,
        },
    )

class PointNeuronPopulationNeuronSet(PopulationNeuronSet):
    """Only point neuron node populations are selectable."""

    population: str = Field(
        default="",
        title="Population",
        description="Name of the point neuron node population to select from.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.NODE_POPULATION_DROPDOWN,
        },
    )

class VirtualPopulationNeuronSet(PopulationNeuronSet):
    """Only virtual node populations are selectable."""

    population: str = Field(
        default="",
        title="Population",
        description="Name of the virtual node population to select from.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.NODE_POPULATION_DROPDOWN,
        },
    )

