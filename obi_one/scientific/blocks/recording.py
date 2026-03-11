import uuid
from abc import ABC, abstractmethod
from typing import Annotated, ClassVar, Self

import entitysdk
from entitysdk.models.ion_channel_model import IonChannelModel
from pydantic import Field, NonNegativeFloat, PositiveFloat, PrivateAttr, model_validator

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.parametric_multi_values import NonNegativeFloatRange
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import _MIN_TIME_STEP_MILLISECONDS
from obi_one.scientific.library.entity_property_types import EntityType, IonChannelPropertyType
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)


class IonChannelVariableForRecording(OBIBaseModel):
    """Single variable of an ion channel model to be recorded.

    Contains the ion channel ID, variable name, and unit.

    Example (GLOBAL ion channel):
        ion_channel_id: uuid.UUID("...")
        channel_name: "StochKv3"
        variable_name: "ik_StochKv3"
        unit: "mA/cm2"
    """

    ion_channel_id: Annotated[uuid.UUID, Field(description="ID of the ion channel")] | None = None
    variable_name: str = Field(
        description="Name of the variable (e.g., 'vmin_StochKv3', 'gCa_HVAbar_Ca_HVA2', 'cm', 'Ra')"
    )

    _unit: str | None = None

    @property
    def unit(self) -> str | None:
        return self._unit

    def validate_model_and_set_unit(self, db_client: entitysdk.client.Client | None = None) -> Self:
        """Check that the model exists, checks it has the variable name and sets the unit."""
        # this will raise an error if the model is not present
        model = db_client.get_entity(
            entity_id=self.ion_channel_id,
            entity_type=IonChannelModel,
        )

        # expects f"{current}_{ion_channel_suffix}" standard.
        # We have to isolate the current to check its presence in the neuron block RANGE
        # in the metadata
        variable = self.variable_name.split("_")[0]

        msg = (
            f"Could not find variable name {variable} from {self.variable_name} "
            f"in neuron_block.range in the entity metadata for {self.channel_name}"
        )
        if model.neuron_block.range is None:
            raise OBIONEError(msg)
        for range_dict in model.neuron_block.range:
            if variable in range_dict:
                self._unit = range_dict[variable]
                break
        else:
            # if self._unit has not been set, raise the error
            raise OBIONEError(msg)

        return self


class Recording(Block, ABC):
    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set",
        description="Neuron set to record from.",
        json_schema_extra={
            "ui_element": "reference",
            "reference_type": NeuronSetReference.__name__,
        },
    )

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
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "ms",
        },
    )

    _default_node_set: str = PrivateAttr(default="All")

    def config(
        self,
        circuit: Circuit,
        population: str | None = None,
        end_time: NonNegativeFloat | None = None,
        default_node_set: str = "All",
        db_client: entitysdk.client.Client | None = None,
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

        sonata_config = self._generate_config(db_client=db_client)

        if self._end_time <= self._start_time:
            msg = (
                f"Recording '{self.block_name}' for Neuron Set "
                "'{self.neuron_set.block.block_name}': "
                "End time must be later than start time!"
            )
            raise OBIONEError(msg)

        return sonata_config

    @abstractmethod
    def _generate_config(self, db_client: entitysdk.client.Client | None = None) -> dict:
        pass


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
            "ui_element": "float_parameter_sweep",
            "units": "ms",
        },
    )

    end_time: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=100.0,
        description="Recording end time in milliseconds (ms).",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "ms",
        },
    )

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

    def _generate_config(self, db_client: entitysdk.client.Client | None = None) -> dict:
        self._start_time = self.start_time
        self._end_time = self.end_time

        return super()._generate_config(db_client=db_client)


class IonChannelVariableRecording(Recording):
    """Records a variable of an ion channel model for the full length of the experiment."""

    title: ClassVar[str] = "Ion Channel Variable Recording (Full Experiment)"

    # RECORDABLE_VARIABLES has shape {model name: [IonChannelVariableForRecording, ...]}
    variable: IonChannelVariableForRecording = Field(
        title="Ion Channel Variable Name",
        description="Name of the variable to record with its unit, "
        "grouped by ion channel model name.",
        json_schema_extra={
            "ui_element": "select_recordable_ion_channel_variable",
            "property_group": EntityType.IONCHANNELMODEL,
            "property": IonChannelPropertyType.RECORDABLE_VARIABLES,
        },
    )

    def _generate_config(self, db_client: entitysdk.client.Client | None = None) -> dict:
        sonata_config = {}

        if db_client is not None:
            self.variable.validate_model_and_set_unit(db_client)

        sonata_config[self.block_name] = {
            "cells": resolve_neuron_set_ref_to_node_set(self.neuron_set, self._default_node_set),
            "sections": "soma",
            "type": "compartment",
            "compartments": "center",
            "variable_name": self.variable.variable_name,
            "dt": self.dt,
            "start_time": self._start_time,
            "end_time": self._end_time,
        }
        if self.variable.unit is not None:
            sonata_config[self.block_name]["unit"] = self.variable.unit
        return sonata_config
