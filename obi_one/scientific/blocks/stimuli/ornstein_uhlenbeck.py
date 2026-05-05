from typing import ClassVar

from pydantic import Field, NonNegativeFloat, PositiveFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.stimuli.stimulus import ContinuousStimulus
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    resolve_neuron_set_ref_to_node_set,
)


class OrnsteinUhlenbeckCurrentSomaticStimulus(ContinuousStimulus):
    """A current injection based on the Ornstein-Uhlenbeck process."""

    title: ClassVar[str] = "Ornstein-Uhlenbeck Current Clamp (Absolute)"

    _module: str = "ornstein_uhlenbeck"
    _input_type: str = "current_clamp"

    time_constant: PositiveFloat | list[PositiveFloat] = Field(
        default=2.7,
        title="Tau",
        description="The time constant of the Ornstein-Uhlenbeck process.",
        json_schema_extra={
            SchemaKey.UNITS: Units.MILLISECONDS,
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    mean_amplitude: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.1,
        title="Mean Amplitude",
        description="The mean value of current to inject. Given in nanoamps (nA).",
        json_schema_extra={
            SchemaKey.UNITS: Units.NANOAMPS,
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    standard_deviation: PositiveFloat | list[PositiveFloat] = Field(
        default=0.05,
        title="Standard Deviation",
        description="The standard deviation of current to inject. Given in nanoamps (nA).",
        json_schema_extra={
            SchemaKey.UNITS: Units.NANOAMPS,
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    def _single_timestamp_stimulus_config(self, offset_timestamp: NonNegativeFloat) -> dict:
        stim_dict = {
            "delay": offset_timestamp,
            "duration": self.duration,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "module": self._module,
            "input_type": self._input_type,
            "tau": self.time_constant,
            "mean": self.mean_amplitude,
            "sigma": self.standard_deviation,
            "represents_physical_electrode": self._represents_physical_electrode,
        }
        return stim_dict


class OrnsteinUhlenbeckConductanceSomaticStimulus(ContinuousStimulus):
    """A conductance injection based on the Ornstein-Uhlenbeck process."""

    title: ClassVar[str] = "Ornstein-Uhlenbeck Conductance Clamp (Absolute)"

    _module: str = "ornstein_uhlenbeck"
    _input_type: str = "conductance"

    time_constant: PositiveFloat | list[PositiveFloat] = Field(
        default=2.7,
        title="Tau",
        description="The time constant of the Ornstein-Uhlenbeck process.",
        json_schema_extra={
            SchemaKey.UNITS: Units.MILLISECONDS,
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    mean_amplitude: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.001,
        title="Mean Amplitude",
        description="The mean value of conductance to inject. Given in microsiemens (μS).",
        json_schema_extra={
            SchemaKey.UNITS: Units.MICROSIEMENS,
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    standard_deviation: PositiveFloat | list[PositiveFloat] = Field(
        default=0.001,
        title="Standard Deviation",
        description="The standard deviation of conductance to inject. Given in microsiemens (μS).",
        json_schema_extra={
            SchemaKey.UNITS: Units.MICROSIEMENS,
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    reversal_potential: float | list[float] = Field(
        default=0.0,
        title="Reversal Potential",
        description="The reversal potential of the conductance injection.",
        json_schema_extra={
            SchemaKey.UNITS: Units.MILLIVOLTS,
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    def _single_timestamp_stimulus_config(self, offset_timestamp: NonNegativeFloat) -> dict:
        stim_dict = {
            "delay": offset_timestamp,
            "duration": self.duration,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "module": self._module,
            "input_type": self._input_type,
            "tau": self.time_constant,
            "mean": self.mean_amplitude,
            "sigma": self.standard_deviation,
            "reversal": self.reversal_potential,
            "represents_physical_electrode": self._represents_physical_electrode,
        }
        return stim_dict


class RelativeOrnsteinUhlenbeckCurrentSomaticStimulus(ContinuousStimulus):
    """Ornstein-Uhlenbeck current injection as a percentage of each cell's threshold current."""

    title: ClassVar[str] = "Ornstein-Uhlenbeck Current Clamp (Relative)"

    _module: str = "relative_ornstein_uhlenbeck"
    _input_type: str = "current_clamp"

    time_constant: PositiveFloat | list[PositiveFloat] = Field(
        default=2.7,
        title="Tau",
        description="The time constant of the Ornstein-Uhlenbeck process.",
        json_schema_extra={
            SchemaKey.UNITS: Units.MILLISECONDS,
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    mean_percentage_of_threshold_current: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=100.0,
        title="Mean Percentage of Threshold Current",
        description="Signal mean as percentage of a cell's threshold current.",
        json_schema_extra={
            SchemaKey.UNITS: Units.PERCENT,
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    standard_deviation_percentage_of_threshold: PositiveFloat | list[PositiveFloat] = Field(
        default=5.0,
        title="Standard Deviation",
        description="Signal standard deviation as percentage of a cell's threshold current.",
        json_schema_extra={
            SchemaKey.UNITS: Units.PERCENT,
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    def _single_timestamp_stimulus_config(self, offset_timestamp: NonNegativeFloat) -> dict:
        stim_dict = {
            "delay": offset_timestamp,
            "duration": self.duration,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "module": self._module,
            "input_type": self._input_type,
            "tau": self.time_constant,
            "mean_percent": self.mean_percentage_of_threshold_current,
            "sd_percent": self.standard_deviation_percentage_of_threshold,
            "represents_physical_electrode": self._represents_physical_electrode,
        }
        return stim_dict


class RelativeOrnsteinUhlenbeckConductanceSomaticStimulus(ContinuousStimulus):
    """Ornstein-Uhlenbeck conductance injection as a percentage of each cell's input conductance."""

    title: ClassVar[str] = "Ornstein-Uhlenbeck Conductance Clamp (Relative)"

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_INPUT_RESISTANCE_BASED_STIMULI,
            SchemaKey.FALSE_MESSAGE: "Input resistance based stimuli are not supported for "
            "this circuit.",
        },
    }

    _module: str = "relative_ornstein_uhlenbeck"
    _input_type: str = "conductance"

    time_constant: PositiveFloat | list[PositiveFloat] = Field(
        default=2.7,
        title="Tau",
        description="The time constant of the Ornstein-Uhlenbeck process.",
        json_schema_extra={
            SchemaKey.UNITS: Units.MILLISECONDS,
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    mean_percentage_of_cells_input_conductance: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=100.0,
        title="Mean Percentage of Cells' Input Conductance",
        description="Signal mean as percentage of a cell's input conductance.",
        json_schema_extra={
            SchemaKey.UNITS: Units.PERCENT,
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    standard_deviation_percentage_of_cells_input_conductance: (
        PositiveFloat | list[PositiveFloat]
    ) = Field(
        default=5.0,
        title="Standard Deviation",
        description="Signal standard deviation as percentage of a cell's input conductance.",
        json_schema_extra={
            SchemaKey.UNITS: Units.PERCENT,
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    reversal_potential: float | list[float] = Field(
        default=0.0,
        title="Reversal Potential",
        description="The reversal potential of the conductance injection.",
        json_schema_extra={
            SchemaKey.UNITS: Units.MILLIVOLTS,
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    def _single_timestamp_stimulus_config(self, offset_timestamp: NonNegativeFloat) -> dict:
        stim_dict = {
            "delay": offset_timestamp,
            "duration": self.duration,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "module": self._module,
            "input_type": self._input_type,
            "tau": self.time_constant,
            "mean_percent": self.mean_percentage_of_cells_input_conductance,
            "sd_percent": self.standard_deviation_percentage_of_cells_input_conductance,
            "reversal": self.reversal_potential,
            "represents_physical_electrode": self._represents_physical_electrode,
        }
        return stim_dict
