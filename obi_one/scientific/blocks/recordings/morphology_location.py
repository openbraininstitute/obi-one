from typing import Annotated, ClassVar

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
    """Records voltage from a morphology-location target."""

    title: ClassVar[str] = "Morphology Location Voltage Recording"

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

    def config(
        self,
        end_time: NonNegativeFloat | None = None,
        default_node_set: str = "All",
        db_client: entitysdk.client.Client | None = None,
    ) -> dict:
        del default_node_set, db_client

        if end_time is None:
            msg = f"End time must be specified for recording '{self.block_name}'."
            raise OBIONEError(msg)
        self._end_time = end_time

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
