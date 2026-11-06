from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.unions_and_references.point_neuron_populations import (
    POINT_NEURON_POPULATION_REFERENCE_TYPES,
    PointNeuronPopulationReference,
)


class PathwayConnectionProbability(Block):
    """Connection probability of a single pathway between two point-neuron populations.

    Defines one entry of the connection-probability matrix: the probability that a neuron in
    the ``source`` population is connected to a neuron in the ``target`` population. Pathways
    for which no ``PathwayConnectionProbability`` is given default to a probability of 0.0.
    """

    source: PointNeuronPopulationReference = Field(
        description="Reference to the presynaptic (source) point-neuron population.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: POINT_NEURON_POPULATION_REFERENCE_TYPES,
        },
    )
    target: PointNeuronPopulationReference = Field(
        description="Reference to the postsynaptic (target) point-neuron population.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: POINT_NEURON_POPULATION_REFERENCE_TYPES,
        },
    )
    connection_probability: float | list[float] = Field(
        description="Probability that a source neuron connects to a target neuron, in [0, 1).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
