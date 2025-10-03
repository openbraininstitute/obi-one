from abc import ABC
from typing import ClassVar

from pydantic import Field, NonNegativeFloat

from obi_one.core.block import Block


class SynapticManipulation(Block, ABC):
    @staticmethod
    def _get_override_name() -> str:
        pass

    def config(self) -> dict:
        return self._generate_config()

    def _generate_config(self) -> dict:
        sonata_config = {
            "name": self._get_override_name(),
            "source": "All",
            "target": "All",
            "synapse_configure": self._get_synapse_configure(),
        }

        return sonata_config


class ScaleAcetylcholineUSESynapticManipulation(SynapticManipulation):
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
    )

    @staticmethod
    def _get_override_name() -> str:
        return "ach_use"

    def _get_synapse_configure(self) -> str:
        return f"%s.Use *= {self.use_scaling}"


class SynapticMgManipulation(SynapticManipulation):
    """Manipulate the extracellular synaptic magnesium (Mg2+) concentration.

    This is applied for all synapses between biophysical neurons.
    """

    title: ClassVar[str] = "Demo: Synaptic Mg2+ Concentration Manipulation"

    magnesium_value: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=2.4,
        title="Extracellular Magnesium Concentration",
        description="Extracellular calcium concentration in millimoles (mM).",
        units="mM",
    )

    @staticmethod
    def _get_override_name() -> str:
        return "Mg"

    def _get_synapse_configure(self) -> str:
        return f"%s.mg = {self.magnesium_value}"
