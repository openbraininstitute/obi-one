import uuid
from typing import Annotated, ClassVar, Self

import entitysdk
from entitysdk.models.ion_channel_model import IonChannelModel
from pydantic import Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.recordings.base import Recording
from obi_one.scientific.library.entity_property_types import EntityType, IonChannelPropertyType
from obi_one.scientific.unions.unions_combined_neuron_sets import (
    resolve_neuron_set_ref_to_node_set,
)


class IonChannelVariableForRecording(OBIBaseModel):
    """Single variable of an ion channel model to be recorded.

    Contains the ion channel ID, variable name, and unit.

    Example (GLOBAL ion channel):
        ion_channel_id: uuid.UUID("...")
        variable_name: "ik_StochKv3"
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
        model = db_client.get_entity(  # ty:ignore[unresolved-attribute]
            entity_id=self.ion_channel_id,  # ty:ignore[invalid-argument-type]
            entity_type=IonChannelModel,
        )

        # expects f"{current}_{ion_channel_suffix}" standard.
        # We have to isolate the current to check its presence in the neuron block RANGE
        # in the metadata
        variable = self.variable_name.split("_")[0]

        msg = (
            f"Could not find variable name {variable} from {self.variable_name} "
            f"in neuron_block.range in the entity metadata for {model.name}"
        )
        if model.neuron_block.range is None:
            raise OBIONEError(msg)
        non_specific_current = [
            var_name
            for nonspecific in model.neuron_block.nonspecific or []
            for var_name in nonspecific
        ]
        write = [
            var_name
            for useion in model.neuron_block.useion or []
            for var_name in useion.write or []
        ]
        available_variables = set(non_specific_current + write)
        for range_dict in model.neuron_block.range:
            if variable in range_dict:
                self._unit = range_dict[variable]
                break
        else:
            # some metadata are missing the full range data,
            # so for those check WRITE and NONSPECIFIC_CURRENT
            # unfortunately, we won't have the unit for those
            # TODO: fix the metadata for all models and remove this fallback
            if variable in available_variables:
                return self
            # if we cannot find the variable, raise error
            raise OBIONEError(msg)

        return self


class IonChannelVariableRecording(Recording):
    """Records a variable of an ion channel model for the full length of the experiment."""

    title: ClassVar[str] = "Ion Channel Variable Recording (Full Experiment)"

    # RECORDABLE_VARIABLES has shape {model name: [IonChannelVariableForRecording, ...]}
    variable: IonChannelVariableForRecording = Field(
        title="Ion Channel Variable Name",
        description="Name of the variable to record with its unit, "
        "grouped by ion channel model name.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.SELECT_RECORDABLE_ION_CHANNEL_VARIABLE,
            SchemaKey.PROPERTY_GROUP: EntityType.IONCHANNELMODEL,
            SchemaKey.PROPERTY: IonChannelPropertyType.RECORDABLE_VARIABLES,
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
