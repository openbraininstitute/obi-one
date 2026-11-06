from enum import StrEnum
from typing import Literal

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement


class SynapseClass(StrEnum):
    """Synapse class of a point-neuron population."""

    EXC = "EXC"
    INH = "INH"


# The field type for synapse_class. A Literal (not the StrEnum) so pydantic inlines
# ``type: string, enum: ["EXC", "INH"]`` in the schema, which the scan-config editor's
# string_selection widget reads directly (a StrEnum would emit a $ref instead).
SynapseClassLiteral = Literal["EXC", "INH"]


class PointNeuronPopulation(Block):
    """A single point-neuron population of the microcircuit network.

    Groups all parameters that the ``SonataNetwork`` exporter sets per neuronal population:
    the population name, its number of neurons, its external indegree, its synapse class
    (excitatory or inhibitory), the spatial extent within which neuron positions are drawn,
    the mean firing rate used for indegree scaling, and the initial membrane potential
    distribution.

    The spatial extent of each axis is given as a pair of ``*_min`` / ``*_max`` fields (in um);
    neuron positions are drawn uniformly within ``[min, max]`` on each axis.
    """

    population_name: str | list[str] = Field(
        description="Name of the population, used as the 'mtype' of its neurons in the SONATA"
        " output (e.g. 'L23E'). Must be unique across populations.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT},
    )
    num_neurons: int | list[int] = Field(
        description="Number of neurons in the population (before applying the neuron number"
        " scaling factor).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    synapse_class: SynapseClassLiteral = Field(
        default="EXC",
        description="Whether the population is excitatory ('EXC') or inhibitory ('INH'). This"
        " determines the sign of the postsynaptic currents of its outgoing connections.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )
    k_ext: int | list[int] = Field(
        default=0,
        description="Indegree of external (background) connections onto each neuron of the"
        " population.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )
    mean_rate: float | list[float] = Field(
        default=0.0,
        description="Mean firing rate of the population (in spikes/s) in the non-scaled network."
        " Used to adjust weights and DC input when the indegree is scaled.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    thalamic_connection_probability: float | list[float] = Field(
        default=0.0,
        description="Probability that a thalamic neuron connects to a neuron of this population."
        " Entry of the thalamo-cortical connection-probability vector for this population. Only"
        " used when the thalamic input is enabled (see the task's 'num_th_neurons').",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    x_min: float | list[float] = Field(
        default=0.0,
        description="Lower bound (in um) of the interval the x-coordinate of neuron positions is"
        " drawn from uniformly.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    x_max: float | list[float] = Field(
        default=100.0,
        description="Upper bound (in um) of the interval the x-coordinate of neuron positions is"
        " drawn from uniformly.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    y_min: float | list[float] = Field(
        default=0.0,
        description="Lower bound (in um) of the interval the y-coordinate (cortical depth) of"
        " neuron positions is drawn from uniformly.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    y_max: float | list[float] = Field(
        default=100.0,
        description="Upper bound (in um) of the interval the y-coordinate (cortical depth) of"
        " neuron positions is drawn from uniformly.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    z_min: float | list[float] = Field(
        default=0.0,
        description="Lower bound (in um) of the interval the z-coordinate of neuron positions is"
        " drawn from uniformly.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    z_max: float | list[float] = Field(
        default=100.0,
        description="Upper bound (in um) of the interval the z-coordinate of neuron positions is"
        " drawn from uniformly.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    v0_mean: float | list[float] = Field(
        default=-58.0,
        description="Mean of the normal distribution of the initial membrane potential (in mV).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    v0_std: float | list[float] = Field(
        default=10.0,
        description="Standard deviation of the normal distribution of the initial membrane"
        " potential (in mV).",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
