from typing import Literal


from obi_one.core.block import Block

from obi_one.scientific.unions.unions_intracellular_location_sets import IntracellularLocationSetUnion
from obi_one.scientific.unions.unions_extracellular_location_sets import ExtracellularLocationSetUnion

class Recording(Block):
    start_time: float | list[float]
    end_time: float | list[float]

    _sonata_config: dict = {}


    def generate_config(self):
        return self._sonata_config

class VoltageRecording(Recording):
    
    recording_type: str = "voltage"
    dt: float | list[float] = 0.1

class SpikeRecording(Recording):
    recording_type: str= "spike"
    spike_detection_location: Literal['AIS', 'soma']

class IntracellularLocationSetVoltageRecording(VoltageRecording):
    intracellular_location_set: IntracellularLocationSetUnion

    def generate_config(self):
        self._sonata_config = {
            "type": "compartment",
            "sections": self.intracellular_location_set.section,
            "cells":  self.intracellular_location_set.neuron_ids,
            "variable_name": "v",
            "dt": self.dt,
            "compartments": "center",
            "start_time": self.start_time,
            "end_time": self.end_time
        }
        return self._sonata_config

class ExtraceullarLocationSetVoltageRecording(VoltageRecording):
    extracellular_location_set: ExtracellularLocationSetUnion

    