from typing import Annotated, ClassVar, Self

import entitysdk
from pydantic import Field, NonNegativeFloat, PositiveFloat, PrivateAttr, model_validator

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.parametric_multi_values import NonNegativeFloatRange
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.library.constants import MIN_TIMESTEP_MILLISECONDS
from obi_one.scientific.unions_and_references.morphology_locations import (
    MorphologyLocationsReference,
)


class MorphologyLocationVoltageRecording(Block):
    """Records voltage from a morphology-location target for the full length of the experiment."""

    title: ClassVar[str] = "Morphology Location Voltage Recording (Full Experiment)"

    morphology_locations: MorphologyLocationsReference | None = Field(
        title="Morphology Locations",
        description="Morphology-location rule to record from.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [MorphologyLocationsReference.__name__],
        },
    )
    dt: (
        Annotated[NonNegativeFloat, Field(ge=MIN_TIMESTEP_MILLISECONDS)]
        | list[Annotated[NonNegativeFloat, Field(ge=MIN_TIMESTEP_MILLISECONDS)]]
        | Annotated[NonNegativeFloatRange, Field(ge=MIN_TIMESTEP_MILLISECONDS)]
    ) = Field(
        default=0.1,
        title="Timestep",
        description="Interval between recording time steps in milliseconds (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )

    _start_time: NonNegativeFloat = 0.0
    _end_time: PositiveFloat = 100.0
    _materialized_compartment_set_name: str | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def validate_morphology_locations(self) -> "MorphologyLocationVoltageRecording":
        if self.morphology_locations is None:
            msg = "Morphology-location voltage recordings require morphology locations."
            raise ValueError(msg)
        return self

    def set_materialized_compartment_set_target(self, name: str) -> None:
        self._materialized_compartment_set_name = name

    def _apply_recording_window(self, simulation_end_time: NonNegativeFloat) -> None:
        """Record for the whole experiment."""
        self._end_time = simulation_end_time

    def config(
        self,
        simulation_timestep: PositiveFloat,
        end_time: NonNegativeFloat | None = None,
        default_node_set: str = "All",
        db_client: entitysdk.client.Client | None = None,
    ) -> dict:
        # This recording samples on its own `dt`, so the simulation's timestep is not used. It is
        # still accepted, because the generation task calls every recording the same way.
        del simulation_timestep, default_node_set, db_client

        if end_time is None:
            msg = f"End time must be specified for recording '{self.block_name}'."
            raise OBIONEError(msg)
        self._apply_recording_window(end_time)

        if self._materialized_compartment_set_name is None:
            msg = (
                f"Recording '{self.block_name}' targets morphology locations, but no "
                "compartment set was materialized."
            )
            raise OBIONEError(msg)

        if self._end_time <= self._start_time:
            msg = f"Recording '{self.block_name}': End time must be later than start time!"
            raise OBIONEError(msg)

        return {
            self.block_name: {
                "compartment_set": self._materialized_compartment_set_name,
                "type": "compartment_set",
                "variable_name": "v",
                "unit": "mV",
                "dt": self.dt,
                "start_time": self._start_time,
                "end_time": self._end_time,
            }
        }


class TimeWindowMorphologyLocationVoltageRecording(MorphologyLocationVoltageRecording):
    """Records voltage from a morphology-location target over a specified time window."""

    title: ClassVar[str] = "Morphology Location Voltage Recording (Time Window)"

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
        """Check that end time is later than start time, once a sweep has resolved."""
        if isinstance(self.start_time, list) or isinstance(self.end_time, list):
            return self

        if self.end_time <= self.start_time:
            recording_name = f" '{self.block_name}'" if self.has_block_name() else ""
            msg = f"Recording{recording_name}: End time must be later than start time!"
            raise OBIONEError(msg)
        return self

    def _apply_recording_window(self, simulation_end_time: NonNegativeFloat) -> None:
        """Record only over the requested window, whatever the simulation length is."""
        del simulation_end_time
        self._start_time = self.start_time  # ty:ignore[invalid-assignment]
        self._end_time = self.end_time  # ty:ignore[invalid-assignment]
