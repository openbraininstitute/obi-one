from abc import ABC, abstractmethod
from typing import ClassVar, Self

import entitysdk
from entitysdk.types import EntityType
from pydantic import Field, model_validator

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.recordings.base import (
    Recording,
    WindowEndTime,
    WindowStartTime,
    check_time_window,
)
from obi_one.scientific.from_id.extracellular_recording_array_from_id import (
    SimulatableExtracellularRecordingArrayFromID,
)


class ExtracellularElectrodeArrayRecording(Recording, ABC):
    """An LFP recording with an extracellular recording array, summed or per neuron."""

    @property
    @abstractmethod
    def method(self) -> str | None:
        """The SONATA report's `method`. None leaves it out, so the report is per cell."""

    electrode_array: SimulatableExtracellularRecordingArrayFromID = Field(
        title="Extracellular recording array",
        description=(
            "Extracellular recording array to record with. Must have been built for the circuit "
            "being simulated."
        ),
        json_schema_extra={
            SchemaKey.PARAMETER_ORDER_PRIORITY: 100,
            SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
            SchemaKey.ENTITY_QUERY: {
                "type": EntityType.simulatable_extracellular_recording_array,
                SchemaKey.FILTERS: {
                    # A list, not a value: the frontend fills it with the id from VALUE_FROM.
                    "circuit_id": ["circuit_id"],
                },
                SchemaKey.VALUE_FROM: "initialize.circuit",
            },
        },
    )

    def _generate_config(
        self,
        db_client: entitysdk.client.Client | None = None,  # ruff: ignore[unused-method-argument]
    ) -> dict:
        config = {
            self.block_name: {
                "cells": self.node_set,
                "type": "lfp",
                # LFP sums the membrane current over the whole neuron, not just the soma, and the
                # weight matrix holds a weight per segment.
                "sections": "all",
                # The recorded values are volts: the weight matrix's scaling factors are in V/nA,
                # as the SONATA spec defines them, and they multiply membrane currents in nA. This
                # only labels the output; unset, libsonata would label it mV, the default for
                # every report, and the values would read 1000 times too small.
                "unit": "V",
                "dt": self.recording_timestep,
                "start_time": self._start_time,
                "end_time": self._end_time,
                # The weight matrix covers every segment of the circuit, so it is not downloaded
                # here. entitysdk's stage_simulation fetches it when the simulation is run, for
                # every array linked to the Simulation entity, recognising which report it belongs
                # to by this file name and rewriting the path to the staged copy.
                "electrodes_file": f"{self.electrode_array.id_str}.h5",
            }
        }
        if self.method is not None:
            config[self.block_name]["method"] = self.method
        return config


class SummedExtracellularElectrodeArrayRecordingBlock(ExtracellularElectrodeArrayRecording):
    """Records the extracellular signal (LFP) seen by each electrode of a recording array, summed
    over the recorded neurons, for the full length of the experiment.

    The array's weight matrix maps the membrane current of every segment of the recorded neurons
    onto every electrode, so the recorded neuron set must be part of the circuit the array was
    built for. The output holds one trace per electrode for each population of the neuron set.

    LFP recordings need CoreNEURON as the simulator, which cannot apply electric field stimuli.
    """

    title: ClassVar[str] = "Summed extracellular electrode array recording (full experiment)"

    method: ClassVar[str | None] = "sum"


class ExtracellularElectrodeArrayRecordingBlock(ExtracellularElectrodeArrayRecording):
    """Records each recorded neuron's contribution to the extracellular signal (LFP) seen by each
    electrode of a recording array, for the full length of the experiment.

    The array's weight matrix maps the membrane current of every segment of the recorded neurons
    onto every electrode, so the recorded neuron set must be part of the circuit the array was
    built for. The output holds a trace per neuron and electrode.

    LFP recordings need CoreNEURON as the simulator, which cannot apply electric field stimuli.
    """

    title: ClassVar[str] = "Per-neuron extracellular electrode array recording (full experiment)"

    method: ClassVar[str | None] = None


class TimeWindowSummedExtracellularElectrodeArrayRecordingBlock(
    SummedExtracellularElectrodeArrayRecordingBlock
):
    """Records the extracellular signal (LFP) seen by each electrode of a recording array, summed
    over the recorded neurons, over a specified time window.

    The array's weight matrix maps the membrane current of every segment of the recorded neurons
    onto every electrode, so the recorded neuron set must be part of the circuit the array was
    built for. The output holds one trace per electrode for each population of the neuron set.

    LFP recordings need CoreNEURON as the simulator, which cannot apply electric field stimuli.
    """

    title: ClassVar[str] = "Summed extracellular electrode array recording (time window)"

    start_time: WindowStartTime
    end_time: WindowEndTime

    @model_validator(mode="after")
    def check_start_end_time(self) -> Self:
        """Check that end time is later than start time."""
        check_time_window(self, self.start_time, self.end_time)
        return self

    def _generate_config(self, db_client: entitysdk.client.Client | None = None) -> dict:
        self._start_time = self.start_time  # ty:ignore[invalid-assignment]
        self._end_time = self.end_time  # ty:ignore[invalid-assignment]
        return super()._generate_config(db_client=db_client)


class TimeWindowExtracellularElectrodeArrayRecordingBlock(
    ExtracellularElectrodeArrayRecordingBlock
):
    """Records each recorded neuron's contribution to the extracellular signal (LFP) seen by each
    electrode of a recording array, over a specified time window.

    The array's weight matrix maps the membrane current of every segment of the recorded neurons
    onto every electrode, so the recorded neuron set must be part of the circuit the array was
    built for. The output holds a trace per neuron and electrode.

    LFP recordings need CoreNEURON as the simulator, which cannot apply electric field stimuli.
    """

    title: ClassVar[str] = "Per-neuron extracellular electrode array recording (time window)"

    start_time: WindowStartTime
    end_time: WindowEndTime

    @model_validator(mode="after")
    def check_start_end_time(self) -> Self:
        """Check that end time is later than start time."""
        check_time_window(self, self.start_time, self.end_time)
        return self

    def _generate_config(self, db_client: entitysdk.client.Client | None = None) -> dict:
        self._start_time = self.start_time  # ty:ignore[invalid-assignment]
        self._end_time = self.end_time  # ty:ignore[invalid-assignment]
        return super()._generate_config(db_client=db_client)
