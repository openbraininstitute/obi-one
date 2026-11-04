from enum import StrEnum

from pydantic import Field

from obi_one.core.block import Block


class SynapseClass(StrEnum):
    """Synapse class of a point-neuron population."""

    EXC = "EXC"
    INH = "INH"


class PointNeuronPopulation(Block):
    """A single point-neuron population of the microcircuit network.

    Groups all parameters that the ``SonataNetwork`` exporter sets per neuronal population:
    the population name, its number of neurons, its external indegree, its synapse class
    (excitatory or inhibitory), the spatial extent within which neuron positions are drawn,
    the mean firing rate used for indegree scaling, and the initial membrane potential
    distribution.
    """

    population_name: str | list[str] = Field(
        description="Name of the population, used as the 'mtype' of its neurons in the SONATA"
        " output (e.g. 'L23E'). Must be unique across populations."
    )
    num_neurons: int | list[int] = Field(
        description="Number of neurons in the population (before applying the neuron number"
        " scaling factor).",
    )
    synapse_class: SynapseClass | list[SynapseClass] = Field(
        default=SynapseClass.EXC,
        description="Whether the population is excitatory ('EXC') or inhibitory ('INH'). This"
        " determines the sign of the postsynaptic currents of its outgoing connections.",
    )
    k_ext: int | list[int] = Field(
        default=0,
        description="Indegree of external (background) connections onto each neuron of the"
        " population.",
    )
    mean_rate: float | list[float] = Field(
        default=0.0,
        description="Mean firing rate of the population (in spikes/s) in the non-scaled network."
        " Used to adjust weights and DC input when the indegree is scaled.",
    )
    thalamic_connection_probability: float | list[float] = Field(
        default=0.0,
        description="Probability that a thalamic neuron connects to a neuron of this population."
        " Entry of the thalamo-cortical connection-probability vector for this population. Only"
        " used when the thalamic input is enabled (see the task's 'num_th_neurons').",
    )
    x_extent: tuple[float, float] | list[tuple[float, float]] = Field(
        default=(0.0, 100.0),
        description="Interval [min, max] (in um) within which the x-coordinate of neuron"
        " positions is drawn uniformly.",
    )
    y_extent: tuple[float, float] | list[tuple[float, float]] = Field(
        default=(0.0, 100.0),
        description="Interval [min, max] (in um) within which the y-coordinate (cortical depth)"
        " of neuron positions is drawn uniformly.",
    )
    z_extent: tuple[float, float] | list[tuple[float, float]] = Field(
        default=(0.0, 100.0),
        description="Interval [min, max] (in um) within which the z-coordinate of neuron"
        " positions is drawn uniformly.",
    )
    v0_mean: float | list[float] = Field(
        default=-58.0,
        description="Mean of the normal distribution of the initial membrane potential (in mV).",
    )
    v0_std: float | list[float] = Field(
        default=10.0,
        description="Standard deviation of the normal distribution of the initial membrane"
        " potential (in mV).",
    )
