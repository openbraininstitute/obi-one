from abc import ABC, abstractmethod
from typing import Annotated, Self

from pydantic import Field, NonNegativeFloat, model_validator

from obi_one.core.block import Block
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetUnion, NeuronSetBlockReference


class Recording(Block, ABC):
    start_time: Annotated[
        NonNegativeFloat | list[NonNegativeFloat], Field(description="Recording start time in ms.")
    ]
    end_time: Annotated[
        NonNegativeFloat | list[NonNegativeFloat], Field(description="Recording end time in ms.")
    ]
    dt: Annotated[
        NonNegativeFloat | list[NonNegativeFloat],
        Field(description="Interval between recording time steps in ms."),
    ] = 0.1
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


class SomaVoltageRecording(Recording):
    neuron_set: NeuronSetBlockReference = Field(description="Neuron set to record from.")

    def _generate_config(self) -> dict:
        sonata_config = {}

        sonata_config[self.name] = {
            "cells": self.neuron_set.block.name,
            "sections": "soma",
            "type": "compartment",
            "compartments": "center",
            "variable_name": "v",
            "unit": "mV",
            "dt": self.dt,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }
        return sonata_config
