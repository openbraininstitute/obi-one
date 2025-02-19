from .template import SubTemplate
from .circuit_grouping import CircuitGrouping

class Recording(SubTemplate):
    start_time: float | list[float]
    end_time: float | list[float]
    circuit_grouping: CircuitGrouping

    def sonata_config(self):
        self._sonata_config = {
            "type": "compartment",
            "sections": "soma",
            "cells":  "hex0",
            "variable_name": "v",
            "dt": 0.1,
            "compartments": "center",
            "start_time": 1400,
            "end_time": 12000
        }
        return self._sonata_config