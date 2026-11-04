from pydantic import Field

from obi_one.core.block import Block
from obi_one.scientific.unions_and_references.point_neuron_populations import (
    PointNeuronPopulationReference,
)


class PathwayConnectionProbability(Block):
    """Connection probability of a single pathway between two point-neuron populations.

    Defines one entry of the connection-probability matrix: the probability that a neuron in
    the ``source`` population is connected to a neuron in the ``target`` population. Pathways
    for which no ``PathwayConnectionProbability`` is given default to a probability of 0.0.
    """

    source: PointNeuronPopulationReference = Field(
        description="Reference to the presynaptic (source) point-neuron population."
    )
    target: PointNeuronPopulationReference = Field(
        description="Reference to the postsynaptic (target) point-neuron population."
    )
    connection_probability: float | list[float] = Field(
        description="Probability that a source neuron connects to a target neuron, in [0, 1).",
    )
