from abc import ABC, abstractmethod
from typing import Annotated, ClassVar

from pydantic import (
    Field,
    NonNegativeFloat,
    PrivateAttr,
)

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.parametric_multi_values import FloatRange
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.timestamps.single import SingleTimestamp
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import (
    _DEFAULT_PULSE_STIMULUS_LENGTH_MILLISECONDS,
    _DEFAULT_SIMULATION_LENGTH_MILLISECONDS,
    _DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    _MIN_NON_NEGATIVE_FLOAT_VALUE,
    _MIN_TIME_STEP_MILLISECONDS,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)
from obi_one.scientific.unions.unions_timestamps import (
    TimestampsReference,
    resolve_timestamps_ref_to_timestamps_block,
)

# Could be in Stimulus class rather than repeated in SomaticStimulus and SpikeStimulus
# But for now this keeps it below the other Block references in get_populationthe GUI
# Eventually we can make the GUI always show the Block references at the top
_TIMESTAMPS_OFFSET_FIELD = Field(
    default=0.0,
    title="Timestamp Offset",
    description="The offset of the stimulus relative to each timestamp in milliseconds (ms).",
    json_schema_extra={
        SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        SchemaKey.UNITS: Units.MILLISECONDS,
    },
)


class BaseStimulus(Block, ABC):
    _default_node_set: str = PrivateAttr(default="All")
    _default_timestamps: TimestampsReference = PrivateAttr(default=SingleTimestamp(start_time=0.0))

    @abstractmethod
    def _generate_config(self) -> dict:
        pass


class StimulusWithTimestamps(BaseStimulus):
    timestamps: TimestampsReference | None = Field(
        default=None,
        title="Timestamps",
        description="Timestamps at which the stimulus is applied.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: TimestampsReference.__name__,
        },
    )

    timestamp_offset: float | list[float] = _TIMESTAMPS_OFFSET_FIELD

    def _offset_timestamps(self) -> list[float]:
        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )

        offset_timestamps = [
            offset_timestamp
            for _, offset_timestamp in timestamps_block.enumerate_non_negative_offset_timestamps(
                self.timestamp_offset
            )
        ]

        return offset_timestamps

    def _generate_config(self) -> dict:
        sonata_config = {}

        for (
            t_ind,
            offset_timestamp,
        ) in enumerate(self._offset_timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = (
                self._single_timestamp_stimulus_config(offset_timestamp)
            )
        return sonata_config


class StimulusWithDuration(BaseStimulus):
    duration: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=_DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
        title="Duration",
        description="Time duration in milliseconds for how long input is activated.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )


class ContinuousStimulusWithoutTimestamps(BaseStimulus):
    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set",
        description="Neuron set to which the stimulus is applied.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
            SchemaKey.SUPPORTS_VIRTUAL: False,
        },
    )

    _represents_physical_electrode: bool = PrivateAttr(default=False)
    """Default is False. If True, the signal will be implemented \
    using a NEURON IClamp mechanism. The IClamp produce an \
    electrode current which is not included in the calculation of \
    extracellular signals, so this option should be used to \
    represent a physical electrode. If the noise signal represents \
    synaptic input, represents_physical_electrode should be set to \
    False, in which case the signal will be implemented using a \
    MembraneCurrentSource mechanism, which is identical to IClamp, \
    but produce a membrane current, which is included in the \
    calculation of the extracellular signal."""

    def config(
        self,
        circuit: Circuit,
        population: str | None = None,
        default_node_set: str = "All",
        default_timestamps: TimestampsReference = None,
    ) -> dict:
        self._default_node_set = default_node_set
        if default_timestamps is None:
            default_timestamps = SingleTimestamp(start_time=0.0)
        self._default_timestamps = default_timestamps

        if (self.neuron_set is not None) and (
            self.neuron_set.block.population_type(circuit, population)
            not in {"biophysical", "point_process", "point_neuron"}
        ):
            msg = (
                f"Neuron Set '{self.neuron_set.block.block_name}' for {self.__class__.__name__}: "
                f"'{self.block_name}' should be biophysical or point_process!"
            )
            raise OBIONEError(msg)

        return self._generate_config()


class ContinuousStimulus(
    ContinuousStimulusWithoutTimestamps, StimulusWithTimestamps, StimulusWithDuration
):
    pass


class ConstantCurrentClampSomaticStimulus(ContinuousStimulus):
    """A constant current injection at a fixed absolute amplitude."""

    title: ClassVar[str] = "Constant Somatic Current Clamp (Absolute)"

    _module: str = "linear"
    _input_type: str = "current_clamp"

    amplitude: float | list[float] | FloatRange = Field(
        default=0.1,
        description="The injected current. Given in nanoamps.",
        title="Amplitude",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.NANOAMPS,
        },
    )

    def _single_timestamp_stimulus_config(self, offset_timestamp: NonNegativeFloat) -> dict:
        stim_dict = {
            "delay": offset_timestamp,
            "duration": self.duration,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "module": self._module,
            "input_type": self._input_type,
            "amp_start": self.amplitude,
            "represents_physical_electrode": self._represents_physical_electrode,
        }
        return stim_dict


class RelativeConstantCurrentClampSomaticStimulus(ContinuousStimulus):
    """A constant current injection at a percentage of each cell's threshold current."""

    title: ClassVar[str] = "Constant Somatic Current Clamp (Relative)"

    _module: str = "relative_linear"
    _input_type: str = "current_clamp"

    percentage_of_threshold_current: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=10.0,
        title="Percentage of Threshold Current",
        description="The percentage of a cell's threshold current to inject when the stimulus \
                    activates.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.PERCENT,
        },
    )

    def _single_timestamp_stimulus_config(self, offset_timestamp: NonNegativeFloat) -> dict:
        stim_dict = {
            "delay": offset_timestamp,
            "duration": self.duration,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "module": self._module,
            "input_type": self._input_type,
            "percent_start": self.percentage_of_threshold_current,
            "represents_physical_electrode": self._represents_physical_electrode,
        }
        return stim_dict


class LinearCurrentClampSomaticStimulus(ContinuousStimulus):
    """A current injection which changes linearly in absolute ampltude over time."""

    title: ClassVar[str] = "Linear Somatic Current Clamp (Absolute)"

    _module: str = "linear"
    _input_type: str = "current_clamp"

    amplitude_start: float | list[float] = Field(
        default=0.1,
        title="Start Amplitude",
        description="The amount of current initially injected when the stimulus activates. "
        "Given in nanoamps.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.NANOAMPS,
        },
    )
    amplitude_end: float | list[float] = Field(
        default=0.2,
        title="End Amplitude",
        description="If given, current is interpolated such that current reaches this value when "
        "the stimulus concludes. Otherwise, current stays at 'Start Amplitude'. Given in nanoamps.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.NANOAMPS,
        },
    )

    def _single_timestamp_stimulus_config(self, offset_timestamp: NonNegativeFloat) -> dict:
        stim_dict = {
            "delay": offset_timestamp,
            "duration": self.duration,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "module": self._module,
            "input_type": self._input_type,
            "amp_start": self.amplitude_start,
            "amp_end": self.amplitude_end,
            "represents_physical_electrode": self._represents_physical_electrode,
        }
        return stim_dict


class RelativeLinearCurrentClampSomaticStimulus(ContinuousStimulus):
    """A current injection which changes linearly as a percentage of each cell's threshold current
    over time.
    """

    title: ClassVar[str] = "Linear Somatic Current Clamp (Relative)"

    _module: str = "relative_linear"
    _input_type: str = "current_clamp"

    percentage_of_threshold_current_start: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=10.0,
        description="The percentage of a cell's threshold current to inject "
        "when the stimulus activates.",
        title="Percentage of Threshold Current (Start)",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.PERCENT,
        },
    )
    percentage_of_threshold_current_end: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=100.0,
        description="If given, the percentage of a cell's threshold current is interpolated such "
        "that the percentage reaches this value when the stimulus concludes.",
        title="Percentage of Threshold Current (End)",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.PERCENT,
        },
    )

    def _single_timestamp_stimulus_config(self, offset_timestamp: NonNegativeFloat) -> dict:
        stim_dict = {
            "delay": offset_timestamp,
            "duration": self.duration,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "module": self._module,
            "input_type": self._input_type,
            "percent_start": self.percentage_of_threshold_current_start,
            "percent_end": self.percentage_of_threshold_current_end,
            "represents_physical_electrode": self._represents_physical_electrode,
        }
        return stim_dict


class NormallyDistributedCurrentClampSomaticStimulus(ContinuousStimulus):
    """Normally distributed current injection with a mean absolute amplitude."""

    title: ClassVar[str] = "Normally Distributed Somatic Current Clamp (Absolute)"

    _module: str = "noise"
    _input_type: str = "current_clamp"

    mean_amplitude: float | list[float] = Field(
        default=0.01,
        description="The mean value of current to inject. Given in nanoamps (nA).",
        title="Mean Amplitude",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.NANOAMPS,
        },
    )
    variance: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.01,
        description="The variance around the mean of current to inject using a \
                    normal distribution.",
        title="Variance",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.NANOAMPS_SQUARED,
        },
    )

    def _single_timestamp_stimulus_config(self, offset_timestamp: NonNegativeFloat) -> dict:
        stim_dict = {
            "delay": offset_timestamp,
            "duration": self.duration,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "module": self._module,
            "input_type": self._input_type,
            "mean": self.mean_amplitude,
            "variance": self.variance,
            "represents_physical_electrode": self._represents_physical_electrode,
        }
        return stim_dict


class RelativeNormallyDistributedCurrentClampSomaticStimulus(ContinuousStimulus):
    """Normally distributed current injection around a mean percentage of each cell's threshold
    current.
    """

    title: ClassVar[str] = "Normally Distributed Somatic Current Clamp (Relative)"

    _module: str = "noise"
    _input_type: str = "current_clamp"

    mean_percentage_of_threshold_current: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.01,
        description="The mean value of current to inject as a percentage of a cell's \
                    threshold current.",
        title="Percentage of Threshold Current (Mean)",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.PERCENT,
        },
    )
    variance: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.01,
        description="The variance around the mean of current to inject using a \
                    normal distribution.",
        title="Variance",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.NANOAMPS_SQUARED,
        },
    )

    def _single_timestamp_stimulus_config(self, offset_timestamp: NonNegativeFloat) -> dict:
        stim_dict = {
            "delay": offset_timestamp,
            "duration": self.duration,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "module": self._module,
            "input_type": self._input_type,
            "mean_percent": self.mean_percentage_of_threshold_current,
            "variance": self.variance,
            "represents_physical_electrode": self._represents_physical_electrode,
        }
        return stim_dict


class MultiPulseCurrentClampSomaticStimulus(ContinuousStimulus):
    """A series of current pulses injected at a fixed frequency, with each pulse having a fixed
    absolute amplitude and temporal width.
    """

    title: ClassVar[str] = "Multi Pulse Somatic Current Clamp (Absolute)"

    _module: str = "pulse"
    _input_type: str = "current_clamp"

    amplitude: float | list[float] = Field(
        default=0.1,
        description="The amount of current initially injected when each pulse activates. "
        "Given in nanoamps (nA).",
        title="Amplitude",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.NANOAMPS,
        },
    )
    width: (
        Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]
        | list[Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]]
    ) = Field(
        default=_DEFAULT_PULSE_STIMULUS_LENGTH_MILLISECONDS,
        description="The length of time each pulse lasts. Given in milliseconds (ms).",
        title="Pulse Width",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    frequency: (
        Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]
        | list[Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]]
    ) = Field(
        default=1.0,
        description="The frequency of pulse trains. Given in Hertz (Hz).",
        title="Pulse Frequency",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )

    def _single_timestamp_stimulus_config(self, offset_timestamp: NonNegativeFloat) -> dict:
        stim_dict = {
            "delay": offset_timestamp,
            "duration": self.duration,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "module": self._module,
            "input_type": self._input_type,
            "amp_start": self.amplitude,
            "width": self.width,
            "frequency": self.frequency,
            "represents_physical_electrode": self._represents_physical_electrode,
        }
        return stim_dict


class SinusoidalCurrentClampSomaticStimulus(ContinuousStimulus):
    """A sinusoidal current injection with a fixed frequency and maximum absolute amplitude."""

    title: ClassVar[str] = "Sinusoidal Somatic Current Clamp (Absolute)"

    _module: str = "sinusoidal"
    _input_type: str = "current_clamp"

    maximum_amplitude: float | list[float] = Field(
        default=0.1,
        description="The maximum (and starting) amplitude of the sinusoid. Given in nanoamps (nA).",
        title="Maximum Amplitude",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.NANOAMPS,
        },
    )
    frequency: (
        Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]
        | list[Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]]
    ) = Field(
        default=1.0,
        description="The frequency of the waveform. Given in Hertz (Hz).",
        title="Frequency",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )
    dt: (
        Annotated[NonNegativeFloat, Field(ge=_MIN_TIME_STEP_MILLISECONDS)]
        | list[Annotated[NonNegativeFloat, Field(ge=_MIN_TIME_STEP_MILLISECONDS)]]
    ) = Field(
        default=0.025,
        description="Timestep of generated signal in milliseconds (ms).",
        title="Timestep",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    def _single_timestamp_stimulus_config(self, offset_timestamp: NonNegativeFloat) -> dict:
        stim_dict = {
            "delay": offset_timestamp,
            "duration": self.duration,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "module": self._module,
            "input_type": self._input_type,
            "amp_start": self.maximum_amplitude,
            "frequency": self.frequency,
            "dt": self.dt,
            "represents_physical_electrode": self._represents_physical_electrode,
        }
        return stim_dict


class SubthresholdCurrentClampSomaticStimulus(ContinuousStimulus):
    """A subthreshold current injection at a percentage below each cell's threshold current."""

    title: ClassVar[str] = "Subthreshold Somatic Current Clamp (Relative)"

    _module: str = "subthreshold"
    _input_type: str = "current_clamp"

    percentage_below_threshold: float | list[float] = Field(
        default=0.1,
        description="A percentage adjusted from 100 of a cell's threshold current. \
                        E.g. 20 will apply 80\\% of the threshold current. Using a negative \
                            value will give more than 100. E.g. -20 will inject 120\\% of the \
                                threshold current.",
        title="Percentage Below Threshold",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.PERCENT,
        },
    )

    def _single_timestamp_stimulus_config(self, offset_timestamp: NonNegativeFloat) -> dict:
        stim_dict = {
            "delay": offset_timestamp,
            "duration": self.duration,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "module": self._module,
            "input_type": self._input_type,
            "percent_less": self.percentage_below_threshold,
            "represents_physical_electrode": self._represents_physical_electrode,
        }
        return stim_dict


class HyperpolarizingCurrentClampSomaticStimulus(ContinuousStimulus):
    """A hyperpolarizing current injection which brings a cell to base membrance voltage.

    The holding current is pre-defined for each cell.
    """

    title: ClassVar[str] = "Hyperpolarizing Somatic Current Clamp"

    _module: str = "hyperpolarizing"
    _input_type: str = "current_clamp"

    def _single_timestamp_stimulus_config(self, offset_timestamp: NonNegativeFloat) -> dict:
        stim_dict = {
            "delay": offset_timestamp,
            "duration": self.duration,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "module": self._module,
            "input_type": self._input_type,
            "represents_physical_electrode": self._represents_physical_electrode,
        }
        return stim_dict


class SEClampSomaticStimulus(ContinuousStimulusWithoutTimestamps):
    """A voltage clamp injection with three steps at different voltages.

    Warning: Maximum one SEClamp stimulus per location.
    """

    # We only have a simple flat voltage stimulus implemented now for simplicity.
    # A more complex implementation with multi-step stimulus will be implemented later.

    title: ClassVar[str] = "Single Electrode Voltage Clamp 3 Levels Somatic Stimulus"

    _module: str = "seclamp"
    _input_type: str = "voltage_clamp"

    level1_duration: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=_DEFAULT_SIMULATION_LENGTH_MILLISECONDS / 4,
        title="Level 1 Duration",
        description="Duration 1 of SEClamp stimulus (in ms)",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "ms",
        },
    )

    level1_voltage: float | list[float] = Field(
        default=-80.0,
        title="Level 1 Voltage",
        description="Amplitude 1 of SEClamp stimulus (in mV)",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "mV",
        },
    )

    level2_duration: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=_DEFAULT_SIMULATION_LENGTH_MILLISECONDS / 2,
        title="Level 2 Duration",
        description="Duration 2 of SEClamp stimulus (in ms)",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "ms",
        },
    )

    level2_voltage: float | list[float] = Field(
        default=0.0,
        title="Level 2 Voltage",
        description="Amplitude 2 of SEClamp stimulus (in mV)",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "mV",
        },
    )

    level3_duration: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=_DEFAULT_SIMULATION_LENGTH_MILLISECONDS / 4,
        title="Level 3 Duration",
        description="Duration 3 of SEClamp stimulus (in ms)",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "ms",
        },
    )

    level3_voltage: float | list[float] = Field(
        default=-80.0,
        title="Level 3 Voltage",
        description="Amplitude 3 of  SEClamp stimulus (in mV)",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "mV",
        },
    )

    # A duration and voltage combination will be needed for the multi-step implementation
    # this will be done in another class

    def _generate_config(self) -> dict:
        sonata_config = {}
        sonata_config[self.block_name] = {
            # cannot have any delay with SEClamp, so timestamps are used in duration_levels
            "delay": 0,
            "duration": self.level1_duration + self.level2_duration + self.level3_duration,
            "voltage": self.level1_voltage,
            # the delay is used as the duration of 1st voltage at initial_voltage level
            # no need to set duration for step voltage since the SEClamp maintain the voltage
            #  until the clamp is off
            "duration_levels": [0, self.level1_duration, self.level2_duration],
            "voltage_levels": [self.level1_voltage, self.level2_voltage, self.level3_voltage],
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "module": self._module,
            "input_type": self._input_type,
            "represents_physical_electrode": self._represents_physical_electrode,
        }
        return sonata_config
