import os
from pathlib import Path

import numpy as np
import pandas as pd

from abc import ABC, abstractmethod
from typing import Annotated
import h5py

from pydantic import Field

from obi_one.core.block import Block
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetUnion
from obi_one.scientific.unions.unions_timestamps import TimestampsUnion


class Stimulus(Block, ABC):
    timestamps: TimestampsUnion
    simulation_level_name: (
        None | Annotated[str, Field(min_length=1, description="Name within a simulation.")]
    ) = None

    def check_simulation_init(self):
        assert self.simulation_level_name is not None, (
            f"'{self.__class__.__name__}' initialization within a simulation required!"
        )

    @property
    def name(self):
        self.check_simulation_init()
        return self.simulation_level_name

    def config(self) -> dict:
        self.check_simulation_init()
        return self._generate_config()

    @abstractmethod
    def _generate_config(self) -> dict:
        pass


class SomaticStimulus(Stimulus, ABC):
    delay: float | list[float] = Field(
        default=0.0, title="Delay", description="Time in ms when input is activated."
    )
    duration: float | list[float] = Field(
        default=1.0,
        title="Duration",
        description="Time duration in ms for how long input is activated.",
    )
    neuron_set: NeuronSetUnion = Field(description="Neuron set to which the stimulus is applied.")
    represents_physical_electrode: bool = Field(
        default=False,
        description="Default is False. If True, the signal will be implemented \
                        using a NEURON IClamp mechanism. The IClamp produce an \
                        electrode current which is not included in the calculation of \
                        extracellular signals, so this option should be used to \
                        represent a physical electrode. If the noise signal represents \
                        synaptic input, represents_physical_electrode should be set to \
                        False, in which case the signal will be implemented using a \
                        MembraneCurrentSource mechanism, which is identical to IClamp, \
                        but produce a membrane current, which is included in the \
                        calculation of the extracellular signal.",
    )


class ConstantCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "linear"
    _input_type: str = "current_clamp"

    amplitude: float | list[float] = Field(
        default=0.1, description="The injected current. Given in nA."
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = {
                "delay": timestamp,
                "duration": self.duration,
                "cells": self.neuron_set.name,
                "module": self._module,
                "input_type": self._input_type,
                "amp_start": self.amplitude,
                "represents_physical_electrode": self.represents_physical_electrode,
            }
        return sonata_config


class LinearCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "linear"
    _input_type: str = "current_clamp"

    amplitude_start: float | list[float] = Field(
        default=0.1,
        description="The amount of current initially injected when the stimulus activates. Given in nA.",
    )
    amplitude_end: float | list[float] = Field(
        default=0.2,
        description="If given, current is interpolated such that current reaches this value when the stimulus concludes. Otherwise, current stays at amp_start. Given in nA",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = {
                "delay": timestamp,
                "duration": self.duration,
                "cells": self.neuron_set.name,
                "module": self._module,
                "input_type": self._input_type,
                "amp_start": self.amplitude_start,
                "amp_end": self.amplitude_end,
                "represents_physical_electrode": self.represents_physical_electrode,
            }
        return sonata_config


class RelativeConstantCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "relative_linear"
    _input_type: str = "current_clamp"

    percentage_of_threshold_current: float | list[float] = Field(
        default=10.0,
        description="The percentage of a cell’s threshold current to inject when the stimulus \
                    activates.",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = {
                "delay": timestamp,
                "duration": self.duration,
                "cells": self.neuron_set.name,
                "module": self._module,
                "input_type": self._input_type,
                "percent_start": self.percentage_of_threshold_current,
                "represents_physical_electrode": self.represents_physical_electrode,
            }
        return sonata_config


class RelativeLinearCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "relative_linear"
    _input_type: str = "current_clamp"

    percentage_of_threshold_current_start: float | list[float] = Field(
        default=10.0,
        description="The percentage of a cell's threshold current to inject when the stimulus activates.",
    )
    percentage_of_threshold_current_end: float | list[float] = Field(
        default=100.0,
        description="If given, the percentage of a cell's threshold current is interpolated such that the percentage reaches this value when the stimulus concludes.",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = {
                "delay": timestamp,
                "duration": self.duration,
                "cells": self.neuron_set.name,
                "module": self._module,
                "input_type": self._input_type,
                "percent_start": self.percentage_of_threshold_current_start,
                "percent_end": self.percentage_of_threshold_current_end,
                "represents_physical_electrode": self.represents_physical_electrode,
            }
        return sonata_config


class MultiPulseCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "pulse"
    _input_type: str = "current_clamp"

    amplitude: float | list[float] = Field(
        default=0.1,
        description="The amount of current initially injected when each pulse activates. Given in nA.",
    )
    width: float | list[float] = Field(
        default=1.0, description="The length of time each pulse lasts. Given in ms."
    )
    frequency: float | list[float] = Field(
        default=1.0, description="The frequency of pulse trains. Given in Hz."
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = {
                "delay": timestamp,
                "duration": self.duration,
                "cells": self.neuron_set.name,
                "module": self._module,
                "input_type": self._input_type,
                "amp_start": self.amplitude,
                "width": self.width,
                "frequency": self.frequency,
                "represents_physical_electrode": self.represents_physical_electrode,
            }
        return sonata_config


class SinusoidalCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "sinusoidal"
    _input_type: str = "current_clamp"

    peak_amplitude: float | list[float] = Field(
        default=0.1, description="The peak amplitude of the sinusoid. Given in nA."
    )
    frequency: float | list[float] = Field(
        default=1.0, description="The frequency of the waveform. Given in Hz."
    )
    dt: float | list[float] = Field(
        default=0.025, description="Timestep of generated signal in ms. Default is 0.025 ms."
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = {
                "delay": timestamp,
                "duration": self.duration,
                "cells": self.neuron_set.name,
                "module": self._module,
                "input_type": self._input_type,
                "amp_start": self.peak_amplitude,
                "frequency": self.frequency,
                "dt": self.dt,
                "represents_physical_electrode": self.represents_physical_electrode,
            }
        return sonata_config


class SubthresholdCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "subthreshold"
    _input_type: str = "current_clamp"

    percentage_below_threshold: float | list[float] = Field(
        default=0.1,
        description=r"A percentage adjusted from 100 of a cell's threshold current. \
                        E.g. 20 will apply 80% of the threshold current. Using a negative \
                            value will give more than 100. E.g. -20 will inject 120% of the \
                                threshold current.",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = {
                "delay": timestamp,
                "duration": self.duration,
                "cells": self.neuron_set.name,
                "module": self._module,
                "input_type": self._input_type,
                "percent_less": self.percentage_below_threshold,
                "represents_physical_electrode": self.represents_physical_electrode,
            }
        return sonata_config


class HyperpolarizingCurrentClampSomaticStimulus(SomaticStimulus):
    """A hyperpolarizing current injection which brings a cell to base membrance voltage \
        used in experiments. Note: No additional parameter are needed when using module \
            “hyperpolarizing”. The holding current applied is defined in the cell model.
    """

    _module: str = "hyperpolarizing"
    _input_type: str = "current_clamp"

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = {
                "delay": timestamp,
                "duration": self.duration,
                "cells": self.neuron_set.name,
                "module": self._module,
                "input_type": self._input_type,
                "represents_physical_electrode": self.represents_physical_electrode,
            }
        return sonata_config


class NoiseCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "noise"
    _input_type: str = "current_clamp"

    mean_amplitude: float | list[float] = Field(
        default=0.01, description="The mean value of current to inject. Given in nA."
    )
    variance: float | list[float] = Field(
        default=0.01,
        description="The variance around the mean of current to inject using a \
                    normal distribution.",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = {
                "delay": timestamp,
                "duration": self.duration,
                "cells": self.neuron_set.name,
                "module": self._module,
                "input_type": self._input_type,
                "mean": self.mean_amplitude,
                "variance": self.variance,
                "represents_physical_electrode": self.represents_physical_electrode,
            }
        return sonata_config


class PercentageNoiseCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "noise"
    _input_type: str = "current_clamp"

    mean_percentage_of_threshold_current: float | list[float] = Field(
        default=0.01,
        description="The mean value of current to inject as a percentage of a cell's \
                    threshold current.",
    )
    variance: float | list[float] = Field(
        default=0.01,
        description="The variance around the mean of current to inject using a \
                    normal distribution.",
    )

    def _generate_config(self) -> dict:
        sonata_config = {}

        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = {
                "delay": timestamp,
                "duration": self.duration,
                "cells": self.neuron_set.name,
                "module": self._module,
                "input_type": self._input_type,
                "mean_percent": self.mean_percentage_of_threshold_current,
                "variance": self.variance,
                "represents_physical_electrode": self.represents_physical_electrode,
            }
        return sonata_config


class SynchronousSingleSpikeStimulus(Stimulus):
   spike_probability: float | list[float]


class SpikeStimulus(Stimulus):
    _module: str = "synapse_replay"
    _input_type: str = "spikes"
    stim_duration: float | list[float]
    _spike_file: Path | None = None
    neuron_set: NeuronSetUnion

    def _generate_config(self) -> dict:
        assert self._spike_file is not None
        sonata_config = {}
        sonata_config[self.name] = {
                "delay": 0.0, # If it is present, then the simulation filters out those times that are before the delay
                "duration": self.stim_duration,
                "cells": self.neuron_set.name,
                "module": self._module,
                "input_type": self._input_type,
                "spike_file": str(self._spike_file) # os.path.relpath # 
            }
        
        return sonata_config

    def generate_spikes(self, circuit, population, spike_file_path):
        raise NotImplementedError("Subclasses should implement this method.")

    @staticmethod
    def write_spike_file(gid_spike_map, spike_file, neuron_set):
        """
        Writes SONATA output spike trains to file.
        
        Spike file format specs: https://github.com/AllenInstitute/sonata/blob/master/docs/SONATA_DEVELOPER_GUIDE.md#spike-file
        """
        # IMPORTANT: Convert SONATA node IDs (0-based) to NEURON cell IDs (1-based)!!
        # (See https://sonata-extension.readthedocs.io/en/latest/blueconfig-projection-example.html#dat-spike-files)
        gid_spike_map = {k + 1: v for k, v in gid_spike_map.items()}
    
        out_path = os.path.split(spike_file)[0]
        if not os.path.exists(out_path):
            os.makedirs(out_path)

        popul_name = neuron_set.name
        time_list = []
        gid_list = []
        for gid, spike_times in gid_spike_map.items():
            if spike_times is not None:
                for t in spike_times:
                    time_list.append(t)
                    gid_list.append(gid)
        spike_df = pd.DataFrame(np.array([time_list, gid_list]).T, columns=['t', 'gid'])
        spike_df = spike_df.astype({'t': float, 'gid': int})
        spike_df.sort_values(by=['t', 'gid'], inplace=True)  # Sort by time
        with h5py.File(spike_file, 'w') as f:
            pop = f.create_group(f"/spikes/{popul_name}")
            ts = pop.create_dataset("timestamps", data=spike_df['t'].values, dtype=np.float64)
            nodes = pop.create_dataset("node_ids", data=spike_df['gid'].values, dtype=np.uint64)
            ts.attrs['units'] = 'ms'

class PoissonSpikeStimulus(SpikeStimulus):
    _module: str = "synapse_replay"
    _input_type: str = "spikes"
    random_seed: int | list[int] = 0
    frequency: float | list[float] = Field(default=0.0, title="Frequency", description="Mean frequency (Hz) of the Poisson input" )
    
    def generate_spikes(self, circuit, population, spike_file_path):
        rng = np.random.default_rng(self.random_seed)
        gids = self.neuron_set.get_neuron_ids(circuit, population)
        gid_spike_map = {}
        timestamps = self.timestamps.timestamps()
        for t_idx, start_time in enumerate(timestamps):
            end_time = start_time + self.stim_duration
            if t_idx < len(timestamps) - 1:
                # Check that interval not overlapping with next stimulus onset
                assert end_time < timestamps[t_idx + 1], "Stimulus time intervals overlap!"
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
                    gid_spike_map[gid] = gid_spike_map[gid] + spikes
                else:
                    gid_spike_map[gid] = spikes
        self._spike_file = f"{self.name}_spikes.h5"
        self.write_spike_file(gid_spike_map, spike_file_path / self._spike_file, self.neuron_set)
        
