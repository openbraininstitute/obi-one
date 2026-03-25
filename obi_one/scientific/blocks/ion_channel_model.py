from typing import ClassVar

from entitysdk.types import EntityType
from pydantic import Field, NonNegativeFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID


class IonChannelModelWithConductance(Block):
    """Select an ion channel model with a conductance parameter."""

    title: ClassVar[str] = "Ion channel model with conductance"

    ion_channel_model: IonChannelModelFromID = Field(
        title="Ion channel model",
        description="ID of the model to simulate.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
            SchemaKey.ENTITY_QUERY: {
                "type": EntityType.ion_channel_model,
                SchemaKey.FILTERS: {
                    "conductance_name__isnull": False,
                },
            },
        },
    )

    conductance: NonNegativeFloat | list[NonNegativeFloat] = Field(
        title="Conductance value",
        description="Conductance value.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.SIEMENS_PER_CM2,
        },
    )


class IonChannelModelWithMaxPermeability(Block):
    """Select an ion channel model with a maximum permeability parameter."""

    title: ClassVar[str] = "Ion channel model with maximum permeability"

    ion_channel_model: IonChannelModelFromID = Field(
        title="Ion channel model",
        description="ID of the model to simulate.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
            SchemaKey.ENTITY_QUERY: {
                "type": EntityType.ion_channel_model,
                SchemaKey.FILTERS: {
                    "max_permeability_name__isnull": False,
                },
            },
        },
    )

    max_permeability: NonNegativeFloat | list[NonNegativeFloat] = Field(
        title="Maximum permeability value",
        description="Maximum permeability value.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.CENTIMETERS_PER_SECOND,
        },
    )


class IonChannelModelWithoutConductance(Block):
    """Select an ion channel model without conductance nor max permeability parameters."""

    title: ClassVar[str] = "Ion channel model without conductance nor max permeability"

    ion_channel_model: IonChannelModelFromID = Field(
        title="Ion channel model",
        description="ID of the model to simulate.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
            SchemaKey.ENTITY_QUERY: {
                "type": EntityType.ion_channel_model,
                SchemaKey.FILTERS: {
                    "conductance_name__isnull": True,
                    "max_permeability_name__isnull": True,
                },
            },
        },
    )
