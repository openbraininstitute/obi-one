from typing import ClassVar

from pydantic import Field, NonNegativeFloat

from obi_one.core.block import Block
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID


class IonChannelModelWithConductance(Block):
    """Select an ion channel model with a conductance parameter."""

    title: ClassVar[str] = "Ion channel model with conductance"

    ion_channel_model: IonChannelModelFromID = Field(
        title="Ion channel model",
        description="ID of the model to simulate.",
        json_schema_extra={
            "ui_element": "model_selector_single",
            "model_selector_entity_type": "IonChannelModel",
            "model_selector_property_filter": {
                "conductance_name": not None,
            },
        },
    )

    conductance: NonNegativeFloat | list[NonNegativeFloat] = Field(
        title="Conductance value (in S/cm2)",
        description="Conductance value (in S/cm2).",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "S/cm2",
        },
    )


class IonChannelModelWithMaxPermeability(Block):
    """Select an ion channel model with a maximum permeability parameter."""

    title: ClassVar[str] = "Ion channel model with maximum permeability"

    ion_channel_model: IonChannelModelFromID = Field(
        title="Ion channel model",
        description="ID of the model to simulate.",
        json_schema_extra={
            "ui_element": "model_selector_single",
            "model_selector_entity_type": "IonChannelModel",
            "model_selector_property_filter": {
                "max_permeability_name": not None,
            },
        },
    )

    max_permeability: NonNegativeFloat | list[NonNegativeFloat] = Field(
        title="Maximum permeability value (in cm/s)",
        description="Maximum permeability value (in cm/s).",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "cm/s",
        },
    )
