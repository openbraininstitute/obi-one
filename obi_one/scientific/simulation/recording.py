from abc import ABC, abstractmethod
from typing import Annotated, Self, ClassVar

from pydantic import Field, NonNegativeFloat, PositiveFloat, model_validator

from obi_one.core.block import Block
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetUnion, NeuronSetReference
from obi_one.scientific.circuit.circuit import Circuit
from obi_one.core.exception import OBIONE_Error


class Recording(Block, ABC):

    neuron_set: Annotated[NeuronSetReference, Field(title="Neuron Set", description="Neuron set to record from.")]

    _start_time: NonNegativeFloat = 0.0
    _end_time: PositiveFloat = 100.0

    dt: Annotated[
        PositiveFloat | list[PositiveFloat],
        Field(default=0.1,
            title="Timestep",
            description="Interval between recording time steps in milliseconds (ms).", units="ms"),
    ]

    def config(self, circuit: Circuit, population: str | None=None, end_time: NonNegativeFloat | None = None) -> dict:
        self.check_simulation_init()

        if self.neuron_set.block.population_type(circuit, population) != "biophysical":
            raise OBIONE_Error(
                f"Neuron Set '{self.neuron_set.block.name}' for {self.__class__.__name__}: \'{self.name}\' should be biophysical!"
            )
        
        if end_time is None:
            raise OBIONE_Error(f"End time must be specified for recording '{self.name}'.")
        self._end_time = end_time

        sonata_config = self._generate_config()

        if self._end_time <= self._start_time:
            raise OBIONE_Error(
                f"Recording '{self.name}' for Neuron Set '{self.neuron_set.block.name}': "
                "End time must be later than start time!"
            )
        
        return sonata_config

    @abstractmethod
    def _generate_config(self) -> dict:
        pass


class SomaVoltageRecording(Recording):
    """Records the soma voltage of a neuron set for the full length of the experiment."""

    title: ClassVar[str] = "Soma Voltage Recording (Full Experiment)"

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
            "start_time": self._start_time,
            "end_time": self._end_time,
        }
        return sonata_config
    

class TimeWindowSomaVoltageRecording(SomaVoltageRecording):
    """Records the soma voltage of a neuron set over a specified time window."""

    title: ClassVar[str] = "Soma Voltage Recording (Time Window)"

    start_time: Annotated[
        NonNegativeFloat | list[NonNegativeFloat], Field(default=0.0, description="Recording start time in milliseconds (ms).", units="ms")
    ]
    end_time: Annotated[
        NonNegativeFloat | list[NonNegativeFloat], Field(default=100.0, description="Recording end time in milliseconds (ms).", units="ms")
    ]

    @model_validator(mode="after")
    def check_start_end_time(self) -> Self:
        """Check that end time is later than start time."""
        if self.end_time <= self.start_time:
            if self.has_name():
                recording_name = f" '{self.name}'"
            else:
                recording_name = ""

            if self.neuron_set.has_block() and self.neuron_set.block.has_name():
                neuron_set_name = f" '{self.neuron_set.block.name}'"
            else:
                neuron_set_name = ""

            raise OBIONE_Error(
                f"Recording{recording_name} for Neuron Set{neuron_set_name}: "
                "End time must be later than start time!"
            )
        return self

    def _generate_config(self) -> dict:

        self._start_time = self.start_time
        self._end_time = self.end_time
        
        return super()._generate_config()
