from abc import ABC, abstractmethod
from pydantic import PrivateAttr, Field

from obi_one.core.block import Block
from obi_one.modeling.unions.unions_timestamps import TimestampsUnion
from obi_one.modeling.unions.unions_synapse_set import SynapseSetUnion
from obi_one.modeling.unions.unions_neuron_sets import NeuronSetUnion

# Repeated descriptions
REPRESENTS_PHYSICAL_ELECTRODE_DESCRIPTION = "Default is False. If True, the signal will be implemented using a NEURON IClamp mechanism. The IClamp produce an electrode current which is not included in the calculation of extracellular signals, so this option should be used to represent a physical electrode. If the noise signal represents synaptic input, represents_physical_electrode should be set to False, in which case the signal will be implemented using a MembraneCurrentSource mechanism, which is identical to IClamp, but produce a membrane current, which is included in the calculation of the extracellular signal."


class Stimulus(Block, ABC):
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

    current: float | list[float] = Field(default=0.1, description="The injected current. Given in nA.")
    represents_physical_electrode: bool | list[bool] = Field(default=False, description=REPRESENTS_PHYSICAL_ELECTRODE_DESCRIPTION)

    def generate(self):
        
        sonata_config = {
            "delay": self.delay,
            "duration": self.duration,
            "cells":  self.neuron_set.name,
            "module": self._module,
            "input_type": self._input_type,
            "amp_start": self.current,
            "represents_physical_electrode": self.represents_physical_electrode
        }
        return sonata_config


class LinearCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "linear"
    _input_type: str = "current_clamp"

    current_start: float | list[float] = Field(default=0.1, description="The amount of current initially injected when the stimulus activates. Given in nA.")
    current_end: float | list[float] = Field(default=0.2, description="If given, current is interpolated such that current reaches this value when the stimulus concludes. Otherwise, current stays at amp_start. Given in nA")
    represents_physical_electrode: bool | list[bool] = Field(default=False, description=REPRESENTS_PHYSICAL_ELECTRODE_DESCRIPTION)

    def generate(self):
        
        sonata_config = {
            "delay": self.delay,
            "duration": self.duration,
            "cells":  self.neuron_set.name,
            "module": self._module,
            "input_type": self._input_type,
            "amp_start": self.current_start,
            "amp_end": self.current_end,
            "represents_physical_electrode": self.represents_physical_electrode
        }
        return sonata_config


class RelativeConstantCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "relative_linear"
    _input_type: str = "current_clamp"

    current_percent: float | list[float] = Field(default=10.0, description="The percentage of the maximum current initially injected when the stimulus activates.")
    represents_physical_electrode: bool | list[bool] = Field(default=False, description=REPRESENTS_PHYSICAL_ELECTRODE_DESCRIPTION)

    def generate(self):
        
        sonata_config = {
            "delay": self.delay,
            "duration": self.duration,
            "cells":  self.neuron_set.name,
            "module": self._module,
            "input_type": self._input_type,
            "percent_start": self.current_percent,
            "represents_physical_electrode": self.represents_physical_electrode
        }
        return sonata_config


class RelativeLinearCurrentClampSomaticStimulus(SomaticStimulus):
    _module: str = "relative_linear"
    _input_type: str = "current_clamp"

    percent_start: float | list[float] = Field(default=10.0, description="The percentage of the maximum current initially injected when the stimulus activates.")
    percent_end: float | list[float] = Field(default=100.0, description="If given, The percentage of a cell’s threshold current is interpolated such that the percentage reaches this value when the stimulus concludes. Otherwise, stays at percent_start")
    represents_physical_electrode: bool | list[bool] = Field(default=False, description=REPRESENTS_PHYSICAL_ELECTRODE_DESCRIPTION)

    def generate(self):
        
        sonata_config = {
            "delay": self.delay,
            "duration": self.duration,
            "cells":  self.neuron_set.name,
            "module": self._module,
            "input_type": self._input_type,
            "percent_start": self.percent_start,
            "percent_end": self.percent_end,
            "represents_physical_electrode": self.represents_physical_electrode
        }
        return sonata_config


class SynchronousSingleSpikeStimulus(Stimulus):
    spike_probability: float | list[float]
