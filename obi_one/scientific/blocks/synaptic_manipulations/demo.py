from typing import ClassVar

from pydantic import Field, NonNegativeFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.synaptic_manipulations.base import (
    GlobalVariableInterNeuronSetSynapticManipulation,
    ModSpecificVariableInterNeuronSetSynapticManipulation,
)


class SynapticMgManipulation(ModSpecificVariableInterNeuronSetSynapticManipulation):
    """Manipulate the extracellular synaptic magnesium (Mg2+) concentration.

    This is applied for all synapses between biophysical neurons.
    """

    title: ClassVar[str] = "Demo: Synaptic Mg2+ Concentration Manipulation"

    magnesium_value: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=2.4,
        title="Extracellular Magnesium Concentration",
        description="Extracellular magnesium concentration in millimoles (mM).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLIMOLAR,
        },
    )

    def _get_synapse_configure(self) -> str:
        return f"mg = {self.magnesium_value}"

    @staticmethod
    def _get_modoverride_name() -> str:  # ty:ignore[invalid-method-override]
        return "GluSynapse"


class ScaleAcetylcholineUSESynapticManipulation(GlobalVariableInterNeuronSetSynapticManipulation):
    """Applying a scaling factor to the U_SE parameter.

    The U_SE parameter determines the effect of achetylcholine (ACh) on synaptic release
    probability using the Tsodyks-Markram synaptic model. This is applied for all synapses
    between biophysical neurons.
    """

    title: ClassVar[str] = (
        "Demo: Scale U_SE to Modulate Acetylcholine Effect on Synaptic Release Probability"
    )

    use_scaling: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.7050728631217412,
        title="Scale U_SE (ACh)",
        description="Scale the U_SE (ACh) parameter of the Tsodyks-Markram synaptic model.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    def _get_synapse_configure(self) -> str:
        return f"%s.Use *= {self.use_scaling}"
