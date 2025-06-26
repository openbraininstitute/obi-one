from abc import ABC, abstractmethod
from typing import Annotated, Self, ClassVar

from pydantic import Field, NonNegativeFloat, model_validator

from obi_one.core.block import Block
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetUnion, NeuronSetReference


class Recording(Block, ABC):
    start_time: Annotated[
        NonNegativeFloat | list[NonNegativeFloat], Field(default=0.0, description="Recording start time in milliseconds (ms).", units="ms")
    ]
    end_time: Annotated[
        NonNegativeFloat | list[NonNegativeFloat], Field(default=100.0, description="Recording end time in milliseconds (ms).", units="ms")
    ]
    dt: Annotated[
        NonNegativeFloat | list[NonNegativeFloat],
        Field(default=0.1,
            title="Timestep",
            description="Interval between recording time steps in milliseconds (ms).", units="ms"),
    ] = 0.1

    @model_validator(mode="after")
    def check_times(self) -> Self:
        """Checks start/end times."""
        assert self.end_time > self.start_time, "Recording end time must be later than start time!"
        return self

    def config(self) -> dict:
        self.check_simulation_init()
        return self._generate_config()

    @abstractmethod
    def _generate_config(self) -> dict:
        pass


class SomaVoltageRecording(Recording):
    """Records the soma voltage of a neuron set."""

    title: ClassVar[str] = "Soma Voltage Recording"

    neuron_set: Annotated[NeuronSetReference, Field(title="Neuron Set", description="Neuron set to record from.")]

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
