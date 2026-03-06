from typing import ClassVar

from entitysdk.types import EntityType
from pydantic import Field, NonNegativeFloat

from obi_one.core.block import Block
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID


class IonChannelModelWithoutConductance(Block):
    """Select an ion channel model without conductance nor max permeability parameters."""

    title: ClassVar[str] = "Ion channel model without conductance nor max permeability"

    ion_channel_model: IonChannelModelFromID = Field(
        title="Ion channel model",
        description="ID of the model to simulate.",
        json_schema_extra={
            "ui_element": "model_selector_single",
            "entity_query": {
                "type": EntityType.ion_channel_model,
                "filters": {
                    "conductance_name__isnull": True,
                    "max_permeability_name__isnull": True,
                },
            },
        },
    )


class IonChannelModelWithConductance(Block):
    """Select an ion channel model with a conductance parameter."""

    title: ClassVar[str] = "Ion channel model with conductance"

    ion_channel_model: IonChannelModelFromID = Field(
        title="Ion channel model",
        description="ID of the model to simulate.",
        json_schema_extra={
            "ui_element": "model_selector_single",
            "entity_query": {
                "type": EntityType.ion_channel_model,
                "filters": {
                    "conductance_name__isnull": False,
                },
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
            "entity_query": {
                "type": EntityType.ion_channel_model,
                "filters": {
                    "max_permeability_name__isnull": False,
                },
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
