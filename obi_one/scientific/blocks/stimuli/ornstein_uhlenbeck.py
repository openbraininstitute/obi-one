from typing import ClassVar

from pydantic import Field, NonNegativeFloat, PositiveFloat

from obi_one.scientific.blocks.stimuli.stimulus import SomaticStimulus
from obi_one.scientific.unions.unions_neuron_sets import (
    resolve_neuron_set_ref_to_node_set,
)
from obi_one.scientific.unions.unions_timestamps import (
    resolve_timestamps_ref_to_timestamps_block,
)


class OrnsteinUhlenbeckCurrentSomaticStimulus(SomaticStimulus):
    """A current injection based on the Ornstein-Uhlenbeck process."""

    title: ClassVar[str] = "Ornstein-Uhlenbeck Current Clamp (Absolute)"

    _module: str = "ornstein_uhlenbeck"
    _input_type: str = "current_clamp"

    time_constant: PositiveFloat | list[PositiveFloat] = Field(
        default=2.7,
        title="Tau",
        description="The time constant of the Ornstein-Uhlenbeck process.",
        units="ms",
    )

    mean_amplitude: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.1,
        title="Mean Amplitude",
        description="The mean value of current to inject. Given in nanoamps (nA).",
        units="nA",
    )

    standard_deviation: PositiveFloat | list[PositiveFloat] = Field(
        default=0.05,
        title="Standard Deviation",
        description="The standard deviation of current to inject. Given in nanoamps (nA).",
        units="nA",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )

        for t_ind, timestamp in enumerate(timestamps_block.timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = {
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "module": self._module,
                "input_type": self._input_type,
                "tau": self.time_constant,
                "mean": self.mean_amplitude,
                "sigma": self.standard_deviation,
                "represents_physical_electrode": self._represents_physical_electrode,
            }
        return sonata_config


class OrnsteinUhlenbeckConductanceSomaticStimulus(SomaticStimulus):
    """A conductance injection based on the Ornstein-Uhlenbeck process."""

    title: ClassVar[str] = "Ornstein-Uhlenbeck Conductance Clamp (Absolute)"

    _module: str = "ornstein_uhlenbeck"
    _input_type: str = "conductance"

    time_constant: PositiveFloat | list[PositiveFloat] = Field(
        default=2.7,
        title="Tau",
        description="The time constant of the Ornstein-Uhlenbeck process.",
        units="ms",
    )

    mean_amplitude: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.1,
        title="Mean Amplitude",
        description="The mean value of conductance to inject. Given in nanosiemens (nS).",
        units="nS",
    )

    standard_deviation: PositiveFloat | list[PositiveFloat] = Field(
        default=0.05,
        title="Standard Deviation",
        description="The standard deviation of conductance to inject. Given in nanosiemens (nS).",
        units="nS",
    )

    reversal_potential: float | list[float] = Field(
        default=0.0,
        title="Reversal Potential",
        description="The reversal potential of the conductance injection.",
        units="mV",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )

        for t_ind, timestamp in enumerate(timestamps_block.timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = {
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "module": self._module,
                "input_type": self._input_type,
                "tau": self.time_constant,
                "mean": self.mean_amplitude,
                "sigma": self.standard_deviation,
                "represents_physical_electrode": self._represents_physical_electrode,
            }
        return sonata_config


class RelativeOrnsteinUhlenbeckCurrentSomaticStimulus(SomaticStimulus):
    """Ornstein-Uhlenbeck current injection as a percentage of each cell's threshold current."""

    title: ClassVar[str] = "Ornstein-Uhlenbeck Current Clamp (Relative)"

    _module: str = "relative_ornstein_uhlenbeck"
    _input_type: str = "current_clamp"

    time_constant: PositiveFloat | list[PositiveFloat] = Field(
        default=2.7,
        title="Tau",
        description="The time constant of the Ornstein-Uhlenbeck process.",
        units="ms",
    )

    mean_percentage_of_threshold_current: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=100.0,
        title="Mean Percentage of Threshold Current",
        description="Signal mean as percentage of a cell's threshold current.",
        units="%",
    )

    standard_deviation_percentage_of_threshold: PositiveFloat | list[PositiveFloat] = Field(
        default=5.0,
        title="Standard Deviation",
        description="Signal standard deviation as percentage of a cell's threshold current.",
        units="%",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )

        for t_ind, timestamp in enumerate(timestamps_block.timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = {
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "module": self._module,
                "input_type": self._input_type,
                "tau": self.time_constant,
                "mean_percent": self.mean_percentage_of_threshold_current,
                "sd_percent": self.standard_deviation_percentage_of_threshold,
                "represents_physical_electrode": self._represents_physical_electrode,
            }
        return sonata_config


class RelativeOrnsteinUhlenbeckConductanceSomaticStimulus(SomaticStimulus):
    """Ornstein-Uhlenbeck conductance injection as a percentage of each cell's input conductance."""

    title: ClassVar[str] = "Ornstein-Uhlenbeck Conductance Clamp (Relative)"

    _module: str = "relative_ornstein_uhlenbeck"
    _input_type: str = "conductance"

    time_constant: PositiveFloat | list[PositiveFloat] = Field(
        default=2.7,
        title="Tau",
        description="The time constant of the Ornstein-Uhlenbeck process.",
        units="ms",
    )

    mean_percentage_of_cells_input_conductance: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=100.0,
        title="Mean Percentage of Cells' Input Conductance",
        description="Signal mean as percentage of a cell's input conductance.",
        units="%",
    )

    standard_deviation_percentage_of_cells_input_conductance: (
        PositiveFloat | list[PositiveFloat]
    ) = Field(
        default=5.0,
        title="Standard Deviation",
        description="Signal standard deviation as percentage of a cell's input conductance.",
        units="%",
    )

    reversal_potential: float | list[float] = Field(
        default=0.0,
        title="Reversal Potential",
        description="The reversal potential of the conductance injection.",
        units="mV",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )

        for t_ind, timestamp in enumerate(timestamps_block.timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = {
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "module": self._module,
                "input_type": self._input_type,
                "tau": self.time_constant,
                "mean_percent": self.mean_percentage_of_cells_input_conductance,
                "sd_percent": self.standard_deviation_percentage_of_cells_input_conductance,
                "reversal": self.reversal_potential,
                "represents_physical_electrode": self._represents_physical_electrode,
            }
        return sonata_config
