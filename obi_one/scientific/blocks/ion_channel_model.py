from abc import ABC

from pydantic import Field, NonNegativeFloat

from obi_one.core.block import Block
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID


class IonChannelModel(Block, ABC):
    ion_channel_model: IonChannelModelFromID = Field(
        title="Ion channel model",
        description="ID of the model to simulate.",
        json_schema_extra={
            "ui_element": "model_identifier",
        },
    )


class IonChannelModelWithConductance(IonChannelModel):
    conductance: NonNegativeFloat | list[NonNegativeFloat] = Field(
        title="Conductance value (in S/cm2)",
        description="Conductance value (in S/cm2).",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "S/cm2",
        },
    )


class IonChannelModelWithMaxPermeability(IonChannelModel):
    max_permeability: NonNegativeFloat | list[NonNegativeFloat] = Field(
        title="Maximum permeability value (in cm/s)",
        description="Maximum permeability value (in cm/s).",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "cm/s",
        },
    )
