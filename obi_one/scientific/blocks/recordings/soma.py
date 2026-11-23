from typing import ClassVar, Self

import entitysdk
from pydantic import NonNegativeFloat, model_validator

from obi_one.scientific.blocks.recordings.base import (
    BaseRecording,
    Recording,
    SimulationDtRecording,
    WindowEndTime,
    WindowStartTime,
    check_time_window,
)


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


class SomaVoltageRecording(Recording):
    """Records the soma voltage of a neuron set for the full length of the experiment."""

    title: ClassVar[str] = "Soma voltage recording (full experiment)"

    def _generate_config(
        self,
        db_client: entitysdk.client.Client | None = None,  # ruff: ignore[unused-method-argument]
    ) -> dict:
        return _soma_voltage_report(self, self._start_time, self._end_time)


class TimeWindowSomaVoltageRecording(Recording):
    """Records the soma voltage of a neuron set over a specified time window."""

    title: ClassVar[str] = "Soma voltage recording (time window)"

    start_time: WindowStartTime
    end_time: WindowEndTime

    @model_validator(mode="after")
    def check_start_end_time(self) -> Self:
        """Check that end time is later than start time."""
        check_time_window(self, self.start_time, self.end_time)
        return self

    def _generate_config(
        self,
        db_client: entitysdk.client.Client | None = None,  # ruff: ignore[unused-method-argument]
    ) -> dict:
        self._start_time = self.start_time  # ty:ignore[invalid-assignment]
        self._end_time = self.end_time  # ty:ignore[invalid-assignment]

        return _soma_voltage_report(self, self._start_time, self._end_time)


# The docstring is the block's description in the UI, so it stays user-facing and matches
# SomaVoltageRecording's. Why this variant exists: Brian2 samples its StateMonitor on the
# integration timestep and rejects a report asking for any other interval, so the sampling
# interval is the simulation timestep rather than a parameter of its own.
class SimulationDtSomaVoltageRecording(SimulationDtRecording):
    """Records the soma voltage of a neuron set for the full length of the experiment."""

    title: ClassVar[str] = "Soma voltage recording (full experiment)"

    def _generate_config(
        self,
        db_client: entitysdk.client.Client | None = None,  # ruff: ignore[unused-method-argument]
    ) -> dict:
        return _soma_voltage_report(self, self._start_time, self._end_time)


# As with SimulationDtSomaVoltageRecording above: user-facing docstring, sampling interval taken
# from the simulation rather than a parameter of its own.
class SimulationDtTimeWindowSomaVoltageRecording(SimulationDtRecording):
    """Records the soma voltage of a neuron set over a specified time window."""

    title: ClassVar[str] = "Soma voltage recording (time window)"

    start_time: WindowStartTime
    end_time: WindowEndTime

    @model_validator(mode="after")
    def check_start_end_time(self) -> Self:
        """Check that end time is later than start time."""
        check_time_window(self, self.start_time, self.end_time)
        return self

    def _generate_config(
        self,
        db_client: entitysdk.client.Client | None = None,  # ruff: ignore[unused-method-argument]
    ) -> dict:
        self._start_time = self.start_time  # ty:ignore[invalid-assignment]
        self._end_time = self.end_time  # ty:ignore[invalid-assignment]

        return _soma_voltage_report(self, self._start_time, self._end_time)
