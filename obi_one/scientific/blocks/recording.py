from abc import ABC, abstractmethod
from typing import Annotated, ClassVar, Self

from pydantic import Field, NonNegativeFloat, PositiveFloat, PrivateAttr, model_validator

from obi_one.core.block import Block
from obi_one.core.constants import _MIN_TIME_STEP_MILLISECONDS
from obi_one.core.exception import OBIONEError
from obi_one.core.parametric_multi_values import NonNegativeFloatRange
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)


class Recording(Block, ABC):
    neuron_set: Annotated[
        NeuronSetReference, Field(title="Neuron Set", description="Neuron set to record from.")
    ]

    _start_time: NonNegativeFloat = 0.0
    _end_time: PositiveFloat = 100.0

    dt: (
        Annotated[NonNegativeFloat, Field(ge=_MIN_TIME_STEP_MILLISECONDS)]
        | list[Annotated[NonNegativeFloat, Field(ge=_MIN_TIME_STEP_MILLISECONDS)]]
        | Annotated[NonNegativeFloatRange, Field(ge=_MIN_TIME_STEP_MILLISECONDS)]
    ) = Field(
        default=0.1,
        title="Timestep",
        description="Interval between recording time steps in milliseconds (ms).",
        units="ms",
    )

    _default_node_set: str = PrivateAttr(default="All")

    def config(
        self,
        circuit: Circuit,
        population: str | None = None,
        end_time: NonNegativeFloat | None = None,
        default_node_set: str = "All",
    ) -> dict:
        self._default_node_set = default_node_set

        if (self.neuron_set is not None) and (
            self.neuron_set.block.population_type(circuit, population) != "biophysical"
        ):
            msg = (
                f"Neuron Set '{self.neuron_set.block.block_name}' for {self.__class__.__name__}: "
                f"'{self.block_name}' should be biophysical!"
            )
            raise OBIONEError(msg)

        if end_time is None:
            msg = f"End time must be specified for recording '{self.block_name}'."
            raise OBIONEError(msg)
        self._end_time = end_time

        sonata_config = self._generate_config()

        if self._end_time <= self._start_time:
            msg = (
                f"Recording '{self.block_name}' for Neuron Set "
                "'{self.neuron_set.block.block_name}': "
                "End time must be later than start time!"
            )
            raise OBIONEError(msg)

        return sonata_config

    @abstractmethod
    def _generate_config(self) -> dict:
        pass


class SomaVoltageRecording(Recording):
    """Records the soma voltage of a neuron set for the full length of the experiment."""

    title: ClassVar[str] = "Soma Voltage Recording (Full Experiment)"

    def _generate_config(self) -> dict:
        sonata_config = {}

        sonata_config[self.block_name] = {
            "cells": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
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
        NonNegativeFloat | list[NonNegativeFloat],
        Field(default=0.0, description="Recording start time in milliseconds (ms).", units="ms"),
    ]
    end_time: Annotated[
        NonNegativeFloat | list[NonNegativeFloat],
        Field(default=100.0, description="Recording end time in milliseconds (ms).", units="ms"),
    ]

    @model_validator(mode="after")
    def check_start_end_time(self) -> Self:
        """Check that end time is later than start time."""
        if self.end_time <= self.start_time:
            recording_name = f" '{self.block_name}'" if self.has_name() else ""

            if self.neuron_set.has_block() and self.neuron_set.block.has_name():
                neuron_set_name = f" '{self.neuron_set.block.block_name}'"
            else:
                neuron_set_name = ""

            msg = (
                f"Recording{recording_name} for Neuron Set{neuron_set_name}: "
                "End time must be later than start time!"
            )
            raise OBIONEError(msg)
        return self

    def _generate_config(self) -> dict:
        self._start_time = self.start_time
        self._end_time = self.end_time

        return super()._generate_config()
