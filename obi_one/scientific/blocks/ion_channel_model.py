from abc import ABC
from typing import Any, ClassVar

from pydantic import Field, NonNegativeFloat

from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID


class IonChannelModelWithConductance(Block, ABC):
    ion_channel_model: IonChannelModelFromID = Field(
        ui_element="model_identifier",
        title="Ion channel model",
        description="ID of the model to simulate.",
    )

    conductance: NonNegativeFloat | list[NonNegativeFloat] = Field(
        ui_element="float_parameter_sweep",
        title="Conductance value (in S/cm2)",
        description="Each conductance is associated to an ion channel model.",
        default=0.0,  # for the models without conductance
    )


class IonChannelModelWithConductanceReference(BlockReference):
    """A reference to an IonChannelModelWithConductance block."""

    allowed_block_types: ClassVar[Any] = IonChannelModelWithConductance
