from typing import Annotated, ClassVar, Self

import entitysdk
from pydantic import Field, NonNegativeFloat, model_validator

from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.recordings.base import (
    BaseRecording,
    Recording,
    SimulationDtRecording,
)

_WindowStartTime = Annotated[
    NonNegativeFloat | list[NonNegativeFloat],
    Field(
        default=0.0,
        description="Recording start time in milliseconds (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    ),
]

_WindowEndTime = Annotated[
    NonNegativeFloat | list[NonNegativeFloat],
    Field(
        default=100.0,
        description="Recording end time in milliseconds (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    ),
]


def _soma_voltage_report(
    recording: BaseRecording,
    start_time: NonNegativeFloat,
    end_time: NonNegativeFloat,
) -> dict:
    """Build the SONATA report body shared by every soma voltage recording."""
    return {
        recording.block_name: {
            "cells": recording.node_set,
            "sections": "soma",
            "type": "compartment",
            "compartments": "center",
            "variable_name": "v",
            "unit": "mV",
            "dt": recording.recording_timestep,
            "start_time": start_time,
            "end_time": end_time,
        }
    }


def _check_time_window(
    recording: BaseRecording,
    start_time: NonNegativeFloat | list[NonNegativeFloat],
    end_time: NonNegativeFloat | list[NonNegativeFloat],
) -> None:
    """Check that a recording's window ends later than it starts."""
    if end_time > start_time:  # ty:ignore[unsupported-operator]
        return

    recording_name = f" '{recording.block_name}'" if recording.has_block_name() else ""

    neuron_set = recording.neuron_set
    if neuron_set is not None and neuron_set.has_block() and neuron_set.block.has_block_name():
        neuron_set_name = f" '{neuron_set.block.block_name}'"
    else:
        neuron_set_name = ""

    msg = (
        f"Recording{recording_name} for Neuron Set{neuron_set_name}: "
        "End time must be later than start time!"
    )
    raise OBIONEError(msg)


class SomaVoltageRecording(Recording):
    """Records the soma voltage of a neuron set for the full length of the experiment."""

    title: ClassVar[str] = "Soma Voltage Recording (Full Experiment)"

    def _generate_config(
        self,
        db_client: entitysdk.client.Client | None = None,  # ruff: ignore[unused-method-argument]
    ) -> dict:
        return _soma_voltage_report(self, self._start_time, self._end_time)


class TimeWindowSomaVoltageRecording(Recording):
    """Records the soma voltage of a neuron set over a specified time window."""

    title: ClassVar[str] = "Soma Voltage Recording (Time Window)"

    start_time: _WindowStartTime
    end_time: _WindowEndTime

    @model_validator(mode="after")
    def check_start_end_time(self) -> Self:
        """Check that end time is later than start time."""
        _check_time_window(self, self.start_time, self.end_time)
        return self

    def _generate_config(
        self,
        db_client: entitysdk.client.Client | None = None,  # ruff: ignore[unused-method-argument]
    ) -> dict:
        self._start_time = self.start_time  # ty:ignore[invalid-assignment]
        self._end_time = self.end_time  # ty:ignore[invalid-assignment]

        return _soma_voltage_report(self, self._start_time, self._end_time)


class SimulationDtSomaVoltageRecording(SimulationDtRecording):
    """Records the soma voltage of a neuron set for the full length of the experiment.

    The sampling interval is the simulation timestep. Brian2 samples its ``StateMonitor`` on the
    integration timestep and rejects a report asking for any other interval, so it uses this
    rather than :class:`SomaVoltageRecording`.
    """

    title: ClassVar[str] = "Soma Voltage Recording (Full Experiment)"

    def _generate_config(
        self,
        db_client: entitysdk.client.Client | None = None,  # ruff: ignore[unused-method-argument]
    ) -> dict:
        return _soma_voltage_report(self, self._start_time, self._end_time)


class SimulationDtTimeWindowSomaVoltageRecording(SimulationDtRecording):
    """Records the soma voltage of a neuron set over a specified time window.

    As with :class:`SimulationDtSomaVoltageRecording`, the sampling interval is the simulation
    timestep rather than a parameter of its own.
    """

    title: ClassVar[str] = "Soma Voltage Recording (Time Window)"

    start_time: _WindowStartTime
    end_time: _WindowEndTime

    @model_validator(mode="after")
    def check_start_end_time(self) -> Self:
        """Check that end time is later than start time."""
        _check_time_window(self, self.start_time, self.end_time)
        return self

    def _generate_config(
        self,
        db_client: entitysdk.client.Client | None = None,  # ruff: ignore[unused-method-argument]
    ) -> dict:
        self._start_time = self.start_time  # ty:ignore[invalid-assignment]
        self._end_time = self.end_time  # ty:ignore[invalid-assignment]

        return _soma_voltage_report(self, self._start_time, self._end_time)
