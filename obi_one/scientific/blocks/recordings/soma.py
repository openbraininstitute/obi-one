from typing import ClassVar, Self

import entitysdk
from pydantic import Field, NonNegativeFloat, model_validator

from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.recordings.base import Recording
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    resolve_neuron_set_ref_to_node_set,
)


class SomaVoltageRecording(Recording):
    """Records the soma voltage of a neuron set for the full length of the experiment."""

    title: ClassVar[str] = "Soma Voltage Recording (Full Experiment)"

    def _generate_config(
        self,
        db_client: entitysdk.client.Client | None = None,  # noqa: ARG002
    ) -> dict:
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

    start_time: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        description="Recording start time in milliseconds (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    end_time: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=100.0,
        description="Recording end time in milliseconds (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    @model_validator(mode="after")
    def check_start_end_time(self) -> Self:
        """Check that end time is later than start time."""
        if self.end_time <= self.start_time:  # ty:ignore[unsupported-operator]
            recording_name = f" '{self.block_name}'" if self.has_name() else ""  # ty:ignore[unresolved-attribute]

            if self.neuron_set.has_block() and self.neuron_set.block.has_name():  # ty:ignore[unresolved-attribute]
                neuron_set_name = f" '{self.neuron_set.block.block_name}'"  # ty:ignore[unresolved-attribute]
            else:
                neuron_set_name = ""

            msg = (
                f"Recording{recording_name} for Neuron Set{neuron_set_name}: "
                "End time must be later than start time!"
            )
            raise OBIONEError(msg)
        return self

    def _generate_config(self, db_client: entitysdk.client.Client | None = None) -> dict:
        self._start_time = self.start_time  # ty:ignore[invalid-assignment]
        self._end_time = self.end_time  # ty:ignore[invalid-assignment]

        return super()._generate_config(db_client=db_client)
