from abc import ABC, abstractmethod
from typing import Annotated, Literal, Self

from pydantic import Field, NonNegativeFloat, model_validator

from obi_one.core.block import Block
from obi_one.scientific.unions.unions_extracellular_location_sets import (
    ExtracellularLocationSetUnion,
)
from obi_one.scientific.unions.unions_intracellular_location_sets import (
    IntracellularLocationSetUnion,
)


class Recording(Block, ABC):
    start_time: Annotated[
        NonNegativeFloat | list[NonNegativeFloat], Field(description="Recording start time in ms.")
    ]
    end_time: Annotated[
        NonNegativeFloat | list[NonNegativeFloat], Field(description="Recording end time in ms.")
    ]
    simulation_level_name: (
        None | Annotated[str, Field(min_length=1, description="Name within a simulation.")]
    ) = None

    @model_validator(mode="after")
    def check_times(self) -> Self:
        """Checks start/end times."""
        assert self.end_time > self.start_time, "Recording end time must be later than start time!"
        return self

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


class VoltageRecording(Recording):
    recording_type: str = "voltage"
    dt: float | list[float] = 0.1


class SpikeRecording(Recording):
    recording_type: str = "spike"
    spike_detection_location: Literal["AIS", "soma"]


class IntracellularLocationSetVoltageRecording(VoltageRecording):
    intracellular_location_set: IntracellularLocationSetUnion

    def _generate_config(self) -> dict:
        sonata_config = {
            "type": "compartment",
            "sections": self.intracellular_location_set.section,
            "cells": self.intracellular_location_set.neuron_ids,
            "variable_name": "v",
            "dt": self.dt,
            "compartments": "center",
            "start_time": self.start_time,
            "end_time": self.end_time,
        }
        return sonata_config


class ExtraceullarLocationSetVoltageRecording(VoltageRecording):
    extracellular_location_set: ExtracellularLocationSetUnion
