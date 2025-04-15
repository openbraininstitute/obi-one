from abc import ABC, abstractmethod
from pydantic import PrivateAttr, Field

from obi_one.core.block import Block
from obi_one.modeling.unions.unions_timestamps import TimestampsUnion
from obi_one.modeling.unions.unions_synapse_set import SynapseSetUnion
from obi_one.modeling.unions.unions_neuron_sets import NeuronSetUnion

# Repeated descriptions
REPRESENTS_PHYSICAL_ELECTRODE_DESCRIPTION = "Default is False. If True, the signal will be implemented using a NEURON IClamp mechanism. The IClamp produce an electrode current which is not included in the calculation of extracellular signals, so this option should be used to represent a physical electrode. If the noise signal represents synaptic input, represents_physical_electrode should be set to False, in which case the signal will be implemented using a MembraneCurrentSource mechanism, which is identical to IClamp, but produce a membrane current, which is included in the calculation of the extracellular signal."


class Stimulus(Block, ABC):
    name: str = Field(description="Name of the stimulus.")
    timestamps: TimestampsUnion

    @abstractmethod
    def generate(self):
        pass


# https://sonata-extension.readthedocs.io/en/latest/sonata_simulation.html#pulse-current-clamp

class SomaticStimulus(Stimulus, ABC):
    delay: float | list[float] = Field(default=0.0, title='Delay', description="Time in ms when input is activated.")
    duration: float | list[float] = Field(default=1.0, title='Duration', description="Time duration in ms for how long input is activated.")
    neuron_set: NeuronSetUnion | list[NeuronSetUnion] = Field(description="Neuron set to which the stimulus is applied.")


class ConstantCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "linear"
    _input_type: str = "current_clamp"

    amplitude: float | list[float] = Field(default=0.1, description="The injected current. Given in nA.")
    represents_physical_electrode: bool | list[bool] = Field(default=False, description=REPRESENTS_PHYSICAL_ELECTRODE_DESCRIPTION)

    def generate(self):

        sonata_config = {}
        
        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = 
                {
                    "delay": timestamp,
                    "duration": self.duration,
                    "cells":  self.neuron_set.name,
                    "module": self._module,
                    "input_type": self._input_type,
                    "amp_start": self.amplitude,
                    "represents_physical_electrode": self.represents_physical_electrode
                }
        return sonata_config


class LinearCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "linear"
    _input_type: str = "current_clamp"

    amplitude_start: float | list[float] = Field(default=0.1, description="The amount of current initially injected when the stimulus activates. Given in nA.")
    amplitude_end: float | list[float] = Field(default=0.2, description="If given, current is interpolated such that current reaches this value when the stimulus concludes. Otherwise, current stays at amp_start. Given in nA")
    represents_physical_electrode: bool | list[bool] = Field(default=False, description=REPRESENTS_PHYSICAL_ELECTRODE_DESCRIPTION)

    def generate(self):
        
        sonata_config = {}
        
        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = 
                {
                    "delay": timestamp,
                    "duration": self.duration,
                    "cells":  self.neuron_set.name,
                    "module": self._module,
                    "input_type": self._input_type,
                    "amp_start": self.amplitude_start,
                    "amp_end": self.amplitude_end,
                    "represents_physical_electrode": self.represents_physical_electrode
                }
        return sonata_config


class RelativeConstantCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "relative_linear"
    _input_type: str = "current_clamp"

    percentage_of_threshold_current: float | list[float] = Field(default=10.0, description="The percentage of a cell’s threshold current to inject when the stimulus activates.")
    represents_physical_electrode: bool | list[bool] = Field(default=False, description=REPRESENTS_PHYSICAL_ELECTRODE_DESCRIPTION)

    def generate(self):
        
        sonata_config = {}
        
        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = 
                {
                    "delay": timestamp,
                    "duration": self.duration,
                    "cells":  self.neuron_set.name,
                    "module": self._module,
                    "input_type": self._input_type,
                    "percent_start": self.percentage_of_threshold_current,
                    "represents_physical_electrode": self.represents_physical_electrode
                }
        return sonata_config


class RelativeLinearCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "relative_linear"
    _input_type: str = "current_clamp"

    percentage_of_threshold_current_start: float | list[float] = Field(default=10.0, description="The percentage of a cell’s threshold current to inject when the stimulus activates.")
    percentage_of_threshold_current_end: float | list[float] = Field(default=100.0, description="If given, the percentage of a cell’s threshold current is interpolated such that the percentage reaches this value when the stimulus concludes.")
    represents_physical_electrode: bool | list[bool] = Field(default=False, description=REPRESENTS_PHYSICAL_ELECTRODE_DESCRIPTION)

    def generate(self):
        
        sonata_config = {}
        
        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = 
                {
                    "delay": timestamp,
                    "duration": self.duration,
                    "cells":  self.neuron_set.name,
                    "module": self._module,
                    "input_type": self._input_type,
                    "percent_start": self.percentage_of_threshold_current_start,
                    "percent_end": self.percentage_of_threshold_current_end,
                    "represents_physical_electrode": self.represents_physical_electrode
                }
        return sonata_config


class MultiPulseCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "pulse"
    _input_type: str = "current_clamp"

    amplitude: float | list[float] = Field(default=0.1, description="The amount of current initially injected when each pulse activates. Given in nA.")
    width: float | list[float] = Field(default=1.0, description="The length of time each pulse lasts. Given in ms.")
    frequency: float | list[float] = Field(default=1.0, description="The frequency of pulse trains. Given in Hz.")
    represents_physical_electrode: bool | list[bool] = Field(default=False, description=REPRESENTS_PHYSICAL_ELECTRODE_DESCRIPTION)

    def generate(self):
        
        sonata_config = {}
        
        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = 
                {
                    "delay": timestamp,
                    "duration": self.duration,
                    "cells":  self.neuron_set.name,
                    "module": self._module,
                    "input_type": self._input_type,
                    "amp_start": self.amplitude,
                    "width": self.width,
                    "frequency": self.frequency,
                    "represents_physical_electrode": self.represents_physical_electrode
                }
        return sonata_config


class SinusoidalCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "sinusoidal"
    _input_type: str = "current_clamp"

    peak_amplitude: float | list[float] = Field(default=0.1, description="The peak amplitude of the sinusoid. Given in nA.")
    frequency: float | list[float] = Field(default=1.0, description="The frequency of the waveform. Given in Hz.")
    dt: float | list[float] = Field(default=0.025, description="Timestep of generated signal in ms. Default is 0.025 ms.")
    represents_physical_electrode: bool | list[bool] = Field(default=False, description=REPRESENTS_PHYSICAL_ELECTRODE_DESCRIPTION)

    def generate(self):
        
        sonata_config = {}
        
        for t_ind, timestamp in enumerate(self.timestamps.timestamps()):
            sonata_config[self.name + "_" + str(t_ind)] = 
                {
                    "delay": timestamp,
                    "duration": self.duration,
                    "cells":  self.neuron_set.name,
                    "module": self._module,
                    "input_type": self._input_type,
                    "amp_start": self.peak_amplitude,
                    "frequency": self.frequency,
                    "dt": self.dt,
                    "represents_physical_electrode": self.represents_physical_electrode
                }
        return sonata_config





class SynchronousSingleSpikeStimulus(Stimulus):
    spike_probability: float | list[float]
