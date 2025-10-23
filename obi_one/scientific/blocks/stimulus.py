from abc import ABC, abstractmethod
from pathlib import Path
from typing import Annotated, ClassVar

import h5py
import numpy as np
import pandas as pd
from pydantic import Field, NonNegativeFloat, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.constants import (
    _DEFAULT_PULSE_STIMULUS_LENGTH_MILLISECONDS,
    _DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    _MIN_NON_NEGATIVE_FLOAT_VALUE,
    _MIN_TIME_STEP_MILLISECONDS,
)
from obi_one.core.exception import OBIONEError
from obi_one.core.parametric_multi_values import FloatRange
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)
from obi_one.scientific.unions.unions_timestamps import TimestampsReference

# Could be in Stimulus class rather than repeated in SomaticStimulus and SpikeStimulus
# But for now this keeps it below the other Block references in get_populationthe GUI
# Eventually we can make the GUI always show the Block references at the top
_TIMESTAMPS_OFFSET_FIELD = Field(
    default=0.0,
    title="Timestamp Offset",
    description="The offset of the stimulus relative to each timestamp in milliseconds (ms).",
    units="ms",
)

_MAX_POISSON_SPIKE_LIMIT = 5000000


class Stimulus(Block, ABC):
    timestamps: Annotated[
        TimestampsReference,
        Field(title="Timestamps", description="Timestamps at which the stimulus is applied."),
    ]

    _default_node_set: str = PrivateAttr(default="All")

    @abstractmethod
    def _generate_config(self) -> dict:
        pass


class SomaticStimulus(Stimulus, ABC):
    neuron_set: Annotated[
        NeuronSetReference,
        Field(
            title="Neuron Set",
            description="Neuron set to which the stimulus is applied.",
            supports_virtual=False,
        ),
    ]

    timestamp_offset: float | list[float] | None = _TIMESTAMPS_OFFSET_FIELD

    duration: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=_DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
        title="Duration",
        description="Time duration in milliseconds for how long input is activated.",
        units="ms",
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
        self, circuit: Circuit, population: str | None = None, default_node_set: str = "All"
    ) -> dict:
        self._default_node_set = default_node_set

        if (self.neuron_set is not None) and (
            self.neuron_set.block.population_type(circuit, population) != "biophysical"
        ):
            msg = (
                f"Neuron Set '{self.neuron_set.block.block_name}' for {self.__class__.__name__}: "
                f"'{self.block_name}' should be biophysical!"
            )
            raise OBIONEError(msg)

        return self._generate_config()


class ConstantCurrentClampSomaticStimulus(SomaticStimulus):
    """A constant current injection at a fixed absolute amplitude."""

    title: ClassVar[str] = "Constant Somatic Current Clamp (Absolute)"

    _module: str = "linear"
    _input_type: str = "current_clamp"

    amplitude: float | list[float] | FloatRange = Field(
        default=0.1,
        description="The injected current. Given in nanoamps.",
        title="Amplitude",
        units="nA",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.block.timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = {
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "module": self._module,
                "input_type": self._input_type,
                "amp_start": self.amplitude,
                "represents_physical_electrode": self._represents_physical_electrode,
            }
        return sonata_config


class RelativeConstantCurrentClampSomaticStimulus(SomaticStimulus):
    """A constant current injection at a percentage of each cell's threshold current."""

    title: ClassVar[str] = "Constant Somatic Current Clamp (Relative)"

    _module: str = "relative_linear"
    _input_type: str = "current_clamp"

    percentage_of_threshold_current: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=10.0,
        title="Percentage of Threshold Current",
        description="The percentage of a cell's threshold current to inject when the stimulus \
                    activates.",
        units="%",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.block.timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = {
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "module": self._module,
                "input_type": self._input_type,
                "percent_start": self.percentage_of_threshold_current,
                "represents_physical_electrode": self._represents_physical_electrode,
            }
        return sonata_config


class LinearCurrentClampSomaticStimulus(SomaticStimulus):
    """A current injection which changes linearly in absolute ampltude over time."""

    title: ClassVar[str] = "Linear Somatic Current Clamp (Absolute)"

    _module: str = "linear"
    _input_type: str = "current_clamp"

    amplitude_start: float | list[float] = Field(
        default=0.1,
        title="Start Amplitude",
        description="The amount of current initially injected when the stimulus activates. "
        "Given in nanoamps.",
        units="nA",
    )
    amplitude_end: float | list[float] = Field(
        default=0.2,
        title="End Amplitude",
        description="If given, current is interpolated such that current reaches this value when "
        "the stimulus concludes. Otherwise, current stays at 'Start Amplitude'. Given in nanoamps.",
        units="nA",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.block.timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = {
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "module": self._module,
                "input_type": self._input_type,
                "amp_start": self.amplitude_start,
                "amp_end": self.amplitude_end,
                "represents_physical_electrode": self._represents_physical_electrode,
            }
        return sonata_config


class RelativeLinearCurrentClampSomaticStimulus(SomaticStimulus):
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
        units="%",
    )
    percentage_of_threshold_current_end: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=100.0,
        description="If given, the percentage of a cell's threshold current is interpolated such "
        "that the percentage reaches this value when the stimulus concludes.",
        title="Percentage of Threshold Current (End)",
        units="%",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.block.timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = {
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "module": self._module,
                "input_type": self._input_type,
                "percent_start": self.percentage_of_threshold_current_start,
                "percent_end": self.percentage_of_threshold_current_end,
                "represents_physical_electrode": self._represents_physical_electrode,
            }
        return sonata_config


class NormallyDistributedCurrentClampSomaticStimulus(SomaticStimulus):
    """Normally distributed current injection with a mean absolute amplitude."""

    title: ClassVar[str] = "Normally Distributed Somatic Current Clamp (Absolute)"

    _module: str = "noise"
    _input_type: str = "current_clamp"

    mean_amplitude: float | list[float] = Field(
        default=0.01,
        description="The mean value of current to inject. Given in nanoamps (nA).",
        title="Mean Amplitude",
        units="nA",
    )
    variance: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.01,
        description="The variance around the mean of current to inject using a \
                    normal distribution.",
        title="Variance",
        units="nA^2",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.block.timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = {
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "module": self._module,
                "input_type": self._input_type,
                "mean": self.mean_amplitude,
                "variance": self.variance,
                "represents_physical_electrode": self._represents_physical_electrode,
            }
        return sonata_config


class RelativeNormallyDistributedCurrentClampSomaticStimulus(SomaticStimulus):
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
        units="%",
    )
    variance: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.01,
        description="The variance around the mean of current to inject using a \
                    normal distribution.",
        title="Variance",
        units="nA^2",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.block.timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = {
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "module": self._module,
                "input_type": self._input_type,
                "mean_percent": self.mean_percentage_of_threshold_current,
                "variance": self.variance,
                "represents_physical_electrode": self._represents_physical_electrode,
            }
        return sonata_config


class MultiPulseCurrentClampSomaticStimulus(SomaticStimulus):
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
        units="nA",
    )
    width: (
        Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]
        | list[Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]]
    ) = Field(
        default=_DEFAULT_PULSE_STIMULUS_LENGTH_MILLISECONDS,
        description="The length of time each pulse lasts. Given in milliseconds (ms).",
        title="Pulse Width",
        units="ms",
    )
    frequency: (
        Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]
        | list[Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]]
    ) = Field(
        default=1.0,
        description="The frequency of pulse trains. Given in Hertz (Hz).",
        title="Pulse Frequency",
        units="Hz",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.block.timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = {
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "module": self._module,
                "input_type": self._input_type,
                "amp_start": self.amplitude,
                "width": self.width,
                "frequency": self.frequency,
                "represents_physical_electrode": self._represents_physical_electrode,
            }
        return sonata_config


class SinusoidalCurrentClampSomaticStimulus(SomaticStimulus):
    """A sinusoidal current injection with a fixed frequency and maximum absolute amplitude."""

    title: ClassVar[str] = "Sinusoidal Somatic Current Clamp (Absolute)"

    _module: str = "sinusoidal"
    _input_type: str = "current_clamp"

    maximum_amplitude: float | list[float] = Field(
        default=0.1,
        description="The maximum (and starting) amplitude of the sinusoid. Given in nanoamps (nA).",
        title="Maximum Amplitude",
        units="nA",
    )
    frequency: (
        Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]
        | list[Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]]
    ) = Field(
        default=1.0,
        description="The frequency of the waveform. Given in Hertz (Hz).",
        title="Frequency",
        units="Hz",
    )
    dt: (
        Annotated[NonNegativeFloat, Field(ge=_MIN_TIME_STEP_MILLISECONDS)]
        | list[Annotated[NonNegativeFloat, Field(ge=_MIN_TIME_STEP_MILLISECONDS)]]
    ) = Field(
        default=0.025,
        description="Timestep of generated signal in milliseconds (ms).",
        title="Timestep",
        units="ms",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.block.timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = {
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "module": self._module,
                "input_type": self._input_type,
                "amp_start": self.maximum_amplitude,
                "frequency": self.frequency,
                "dt": self.dt,
                "represents_physical_electrode": self._represents_physical_electrode,
            }
        return sonata_config


class SubthresholdCurrentClampSomaticStimulus(SomaticStimulus):
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
        units="%",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.block.timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = {
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "module": self._module,
                "input_type": self._input_type,
                "percent_less": self.percentage_below_threshold,
                "represents_physical_electrode": self._represents_physical_electrode,
            }
        return sonata_config


class HyperpolarizingCurrentClampSomaticStimulus(SomaticStimulus):
    """A hyperpolarizing current injection which brings a cell to base membrance voltage.

    The holding current is pre-defined for each cell.
    """

    title: ClassVar[str] = "Hyperpolarizing Somatic Current Clamp"

    _module: str = "hyperpolarizing"
    _input_type: str = "current_clamp"

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.block.timestamps()):
            sonata_config[self.block_name + "_" + str(t_ind)] = {
                "delay": timestamp + self.timestamp_offset,
                "duration": self.duration,
                "node_set": resolve_neuron_set_ref_to_node_set(
                    self.neuron_set, self._default_node_set
                ),
                "module": self._module,
                "input_type": self._input_type,
                "represents_physical_electrode": self._represents_physical_electrode,
            }
        return sonata_config


class SpikeStimulus(Stimulus):
    _module: str = "synapse_replay"
    _input_type: str = "spikes"
    _spike_file: Path | None = None
    _simulation_length: float | None = None
    source_neuron_set: Annotated[
        NeuronSetReference, Field(title="Neuron Set (Source)", supports_virtual=True)
    ]
    targeted_neuron_set: Annotated[
        NeuronSetReference, Field(title="Neuron Set (Target)", supports_virtual=False)
    ]

    timestamp_offset: float | list[float] | None = _TIMESTAMPS_OFFSET_FIELD

    def config(
        self, circuit: Circuit, population: str | None = None, default_node_set: str = "All"
    ) -> dict:
        self._default_node_set = default_node_set

        if (self.targeted_neuron_set is not None) and (
            self.targeted_neuron_set.block.population_type(circuit, population) != "biophysical"
        ):
            msg = (
                f"Target Neuron Set '{self.targeted_neuron_set.block.block_name}' for "
                f"{self.__class__.__name__}: '{self.block_name}' should be biophysical!"
            )
            raise OBIONEError(msg)

        return self._generate_config()

    def _generate_config(self) -> dict:
        if self._spike_file is None:
            msg = "Spike file must be set before generating SONATA config"
            raise ValueError(msg)
        if self._simulation_length is None:
            msg = "Simulation length must be set before generating SONATA config"
            " component for SpikeStimulus."
            raise ValueError(msg)
        sonata_config = {}
        sonata_config[self.block_name] = {
            "delay": 0.0,  # If present, the simulation filters out those times before the delay
            "duration": self._simulation_length,
            "node_set": resolve_neuron_set_ref_to_node_set(
                self.targeted_neuron_set, self._default_node_set
            ),
            "module": self._module,
            "input_type": self._input_type,
            "spike_file": str(self._spike_file),  # os.path.relpath #
        }

        return sonata_config

    def generate_spikes(
        self,
        circuit: Circuit,
        spike_file_path: Path,
        simulation_length: NonNegativeFloat,
        source_node_population: str | None = None,
    ) -> None:
        msg = "Subclasses should implement this method."
        raise NotImplementedError(msg)

    @staticmethod
    def write_spike_file(
        gid_spike_map: dict, spike_file: Path, source_node_population: str | None = None
    ) -> None:
        """Writes SONATA output spike trains to file.

        Spike file format specs: https://github.com/AllenInstitute/sonata/blob/master/docs/SONATA_DEVELOPER_GUIDE.md#spike-file
        """
        # IMPORTANT: Convert SONATA node IDs (0-based) to NEURON cell IDs (1-based)!!
        # (See https://sonata-extension.readthedocs.io/en/latest/blueconfig-projection-example.html#dat-spike-files)
        gid_spike_map = {k + 1: v for k, v in gid_spike_map.items()}

        out_path = Path(spike_file).parent
        if not out_path.exists():
            out_path.mkdir(parents=True)

        time_list = []
        gid_list = []
        for gid, spike_times in gid_spike_map.items():
            if spike_times is not None:
                for t in spike_times:
                    time_list.append(t)
                    gid_list.append(gid)
        spike_df = pd.DataFrame(np.array([time_list, gid_list]).T, columns=["t", "gid"])
        spike_df = spike_df.astype({"t": float, "gid": int})
        spike_df_sorted = spike_df.sort_values(by=["t", "gid"])  # Sort by time
        with h5py.File(spike_file, "w") as f:
            pop = f.create_group(f"/spikes/{source_node_population}")
            ts = pop.create_dataset(
                "timestamps", data=spike_df_sorted["t"].values, dtype=np.float64
            )
            pop.create_dataset("node_ids", data=spike_df_sorted["gid"].values, dtype=np.uint64)
            ts.attrs["units"] = "ms"


class PoissonSpikeStimulus(SpikeStimulus):
    """Spike times drawn from a Poisson process with a given frequency.

    Sent from all neurons in the source neuron set to efferently connected
    neurons in the target neuron set.
    """

    title: ClassVar[str] = "Poisson Spikes (Efferent)"

    _module: str = "synapse_replay"
    _input_type: str = "spikes"
    duration: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=_DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
        title="Duration",
        description="Time duration in milliseconds for how long input is activated.",
        units="ms",
    )
    frequency: (
        Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]
        | list[Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]]
    ) = Field(
        default=1.0,
        title="Frequency",
        description="Mean frequency (Hz) of the Poisson input.",
        units="Hz",
    )
    random_seed: int | list[int] = Field(
        default=0,
        title="Random Seed",
        description="Seed for the random number generator to ensure "
        "reproducibility of the spike generation.",
    )

    def generate_spikes(
        self,
        circuit: Circuit,
        spike_file_path: Path,
        simulation_length: NonNegativeFloat,
        source_node_population: str | None = None,
    ) -> None:
        self._simulation_length = simulation_length
        rng = np.random.default_rng(self.random_seed)
        gids = self.source_neuron_set.block.get_neuron_ids(circuit, source_node_population)
        source_node_population = self.source_neuron_set.block.get_population(source_node_population)
        timestamps = self.timestamps.block.timestamps()

        if (
            self.duration * 1e-3 * len(gids) * self.frequency * len(timestamps)
            > _MAX_POISSON_SPIKE_LIMIT
        ):
            msg = (
                f"Poisson input exceeds maximum allowed nunmber of spikes "
                f"({_MAX_POISSON_SPIKE_LIMIT})!"
            )
            raise OBIONEError(msg)

        gid_spike_map = {}
        for timestamp_idx, timestamp_t in enumerate(timestamps):
            start_time = timestamp_t + self.timestamp_offset
            end_time = start_time + self.duration
            if timestamp_idx < len(timestamps) - 1 and not end_time < timestamps[timestamp_idx + 1]:
                msg = "Stimulus time intervals overlap!"
                raise ValueError(msg)
            for gid in gids:
                spikes = []
                t = start_time
                while t < end_time:
                    # Draw next spike time from exponential distribution
                    interval = rng.exponential(1.0 / self.frequency) * 1000  # convert s → ms
                    t += interval
                    if t < end_time:
                        spikes.append(t)
                if gid in gid_spike_map:
                    gid_spike_map[gid] += spikes
                else:
                    gid_spike_map[gid] = spikes
        self._spike_file = f"{self.block_name}_spikes.h5"
        self.write_spike_file(
            gid_spike_map, spike_file_path / self._spike_file, source_node_population
        )


class FullySynchronousSpikeStimulus(SpikeStimulus):
    """Spikes sent at the same time from all neurons in the source neuron set.

    to efferently connected neurons in the target neuron set.
    """

    title: ClassVar[str] = "Fully Synchronous Spikes (Efferent)"

    _module: str = "synapse_replay"
    _input_type: str = "spikes"

    def generate_spikes(
        self,
        circuit: Circuit,
        spike_file_path: Path,
        simulation_length: NonNegativeFloat,
        source_node_population: str | None = None,
    ) -> None:
        self._simulation_length = simulation_length
        gids = self.source_neuron_set.block.get_neuron_ids(circuit, source_node_population)
        source_node_population = self.source_neuron_set.block.get_population(source_node_population)
        gid_spike_map = {}
        timestamps = self.timestamps.block.timestamps()
        for start_time in timestamps:
            spike = [start_time + self.timestamp_offset]
            for gid in gids:
                if gid in gid_spike_map:
                    gid_spike_map[gid] += spike
                else:
                    gid_spike_map[gid] = spike
        self._spike_file = f"{self.block_name}_spikes.h5"
        self.write_spike_file(
            gid_spike_map, spike_file_path / self._spike_file, source_node_population
        )
