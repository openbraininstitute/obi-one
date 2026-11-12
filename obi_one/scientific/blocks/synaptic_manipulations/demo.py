from typing import ClassVar

from pydantic import Field, NonNegativeFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.synaptic_manipulations.base import (
    GlobalVariableInterNeuronSetSynapticManipulation,
)


class ScaleAcetylcholineUSESynapticManipulation(GlobalVariableInterNeuronSetSynapticManipulation):
    """Applying a scaling factor to the U_SE parameter.

    The U_SE parameter determines the effect of achetylcholine (ACh) on synaptic release
    probability using the Tsodyks-Markram synaptic model. This is applied for all synapses
    between biophysical neurons.
    """

    title: ClassVar[str] = (
        "Demo: scale U_SE to modulate acetylcholine effect on synaptic release probability"
    )

    use_scaling: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.7050728631217412,
        title="Scale U_SE (ACh)",
        description="Scale the U_SE (ACh) parameter of the Tsodyks-Markram synaptic model.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    def _get_synapse_configure(self) -> str:
        return f"%s.Use *= {self.use_scaling}"
