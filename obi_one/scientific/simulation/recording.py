from abc import ABC, abstractmethod
from typing import Annotated, Self, ClassVar

from pydantic import Field, NonNegativeFloat, model_validator

from obi_one.core.block import Block
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetUnion, NeuronSetReference
from obi_one.scientific.circuit.circuit import Circuit
from obi_one.core.exception import OBIONE_Error


class Recording(Block, ABC):

    neuron_set: Annotated[NeuronSetReference, Field(title="Neuron Set", description="Neuron set to record from.")]

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

    def config(self, circuit: Circuit, population: str | None=None) -> dict:
        self.check_simulation_init()
        return self._generate_config()

    @abstractmethod
    def _generate_config(self) -> dict:
        pass


class SomaVoltageRecording(Recording):
    """Records the soma voltage of a neuron set."""

    title: ClassVar[str] = "Soma Voltage Recording"

    def config(self, circuit: Circuit, population: str | None=None) -> dict:
        self.check_simulation_init()

        if self.neuron_set.block.population_type(circuit, population) != "biophysical":
            raise OBIONE_Error(
                f"Neuron Set '{self.neuron_set.block.name}' for {self.__class__.__name__}: \'{self.name}\' should be biophysical!"
            )

        return self._generate_config()

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
