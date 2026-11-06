import warnings
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.point_neuron_populations.population import (
    PointNeuronPopulation,
    SynapseClassLiteral,
)

try:
    from microcircuit.network_params import default_net_dict
    from microcircuit.stimulus_params import default_stim_dict
except ImportError:
    warnings.warn(
        "PD14 presets not available (the 'microcircuit' package is not installed).",
        UserWarning,
        stacklevel=1,
    )


class PD14Population(StrEnum):
    """Names of the neuronal populations of the default Potjans & Diesmann (2014) network."""

    L23E = "L23E"
    L23I = "L23I"
    L4E = "L4E"
    L4I = "L4I"
    L5E = "L5E"
    L5I = "L5I"
    L6E = "L6E"
    L6I = "L6I"


# The field type for ``preset``. A Literal (not the StrEnum) so pydantic inlines
# ``type: string, enum: [...]`` in the schema, which the scan-config editor's string_selection
# widget reads directly (a StrEnum would emit a $ref instead).
PD14PopulationLiteral = Literal["L23E", "L23I", "L4E", "L4I", "L5E", "L5I", "L6E", "L6I"]


def _pd14_preset_parameters(preset: str) -> dict:
    """Per-population parameters of the default ``net_dict`` for the given population name."""
    net_dict = default_net_dict
    stim_dict = default_stim_dict
    index = net_dict["populations"].index(preset)
    geometry = net_dict["layer_geometry"][preset]
    # Excitatory / inhibitory alternate in the default model (even index excitatory).
    synapse_class = "EXC" if index % 2 == 0 else "INH"
    return {
        "population_name": preset,
        "num_neurons": int(net_dict["full_num_neurons"][index]),
        "synapse_class": synapse_class,
        "k_ext": int(net_dict["K_ext"][index]),
        "mean_rate": float(net_dict["full_mean_rates"][index]),
        "thalamic_connection_probability": float(stim_dict["conn_probs_th"][index]),
        "x_min": float(geometry["x"][0]),
        "x_max": float(geometry["x"][1]),
        "y_min": float(geometry["y"][0]),
        "y_max": float(geometry["y"][1]),
        "z_min": float(geometry["z"][0]),
        "z_max": float(geometry["z"][1]),
        "v0_mean": float(net_dict["neuron_params"]["V0_mean"]["optimized"][index]),
        "v0_std": float(net_dict["neuron_params"]["V0_std"]["optimized"][index]),
    }


class PD14PointNeuron(PointNeuronPopulation):
    """A point-neuron population preset to a population of the default PD14 network.

    Selecting a ``preset`` (one of the population names of the original ``Network`` class,
    e.g. ``L23E``) fills every ``PointNeuronPopulation`` parameter with the corresponding
    value from the default ``net_dict`` (and the default thalamic connection probability).

    In the scan-config editor only the ``preset`` is shown and selectable; every inherited
    parameter is hidden (``ui_hidden``) and filled from the preset, so the user is "stuck with"
    the preset's values. Outside the editor (programmatic / notebook use) a parameter may still
    be set explicitly to override the preset value.
    """

    preset: PD14PopulationLiteral = Field(
        default="L23E",
        description="Population of the default PD14 network to take the parameters from.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION},
    )

    # The inherited parameters are optional (unset ones are filled from the preset) and hidden
    # in the editor, so the preset is the only thing the user can set there.
    population_name: str | list[str | None] | None = Field(
        default=None,
        description="Name of the population. Defaults to the preset's population name.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    num_neurons: int | list[int | None] | None = Field(
        default=None,
        description="Number of neurons. Defaults to the preset's value.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    synapse_class: SynapseClassLiteral | list[SynapseClassLiteral | None] | None = Field(
        default=None,
        description="Synapse class. Defaults to the preset's value.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    k_ext: int | list[int | None] | None = Field(
        default=None,
        description="External indegree. Defaults to the preset's value.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    mean_rate: float | list[float | None] | None = Field(
        default=None,
        description="Mean firing rate. Defaults to the preset's value.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    thalamic_connection_probability: float | list[float | None] | None = Field(
        default=None,
        description="Thalamo-cortical connection probability. Defaults to the preset's value.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    x_min: float | list[float | None] | None = Field(
        default=None,
        description="x lower bound. Defaults to the preset's value.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    x_max: float | list[float | None] | None = Field(
        default=None,
        description="x upper bound. Defaults to the preset's value.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    y_min: float | list[float | None] | None = Field(
        default=None,
        description="y lower bound. Defaults to the preset's value.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    y_max: float | list[float | None] | None = Field(
        default=None,
        description="y upper bound. Defaults to the preset's value.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    z_min: float | list[float | None] | None = Field(
        default=None,
        description="z lower bound. Defaults to the preset's value.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    z_max: float | list[float | None] | None = Field(
        default=None,
        description="z upper bound. Defaults to the preset's value.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    v0_mean: float | list[float | None] | None = Field(
        default=None,
        description="Mean initial membrane potential. Defaults to the preset's value.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    v0_std: float | list[float | None] | None = Field(
        default=None,
        description="Std of the initial membrane potential. Defaults to the preset's value.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    @model_validator(mode="after")
    def fill_from_preset(self) -> "PD14PointNeuron":
        """Fill unset parameters from the preset's default ``net_dict`` values."""
        defaults = _pd14_preset_parameters(str(self.preset))
        for name, value in defaults.items():
            if getattr(self, name) is None:
                setattr(self, name, value)
        return self
