from abc import ABC, abstractmethod
from obi_one.core.block import Block
from pydantic import Field, NonNegativeFloat
from typing import ClassVar

class SynapticManipulation(Block, ABC):

    @abstractmethod
    def _get_override_name(self) -> str:
        pass

    def config(self) -> dict:
        self.check_simulation_init()
        return self._generate_config()

    def _generate_config(self) -> dict:
        sonata_config = {
            "name": self._get_override_name(),
            "source": "All",
            "target": "All",
            "synapse_configure": self._get_synapse_configure(),
        }

        return sonata_config



class AcetylcholineScalingOfReleaseProbabilitySynapticManiupulation(SynapticManipulation):
    """Manipulate the U_se parameter which scales the effect of achetylcholine (ACh) on synaptic release probability using the Tsodyks–Markram synaptic model.\
        This is applied for all synapses between biophysical neurons."""

    title: ClassVar[str] = "Demo: Acetylcholine Effect on Synaptic Release Probability"

    use: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.7050728631217412,
        title="Scaling Factor U_se",
        description="A scaling factor for the effect of acetylcholine on synaptic release probability.")

    def _get_override_name(self) -> str:
        return "ach_use"

    def _get_synapse_configure(self) -> str:
        return f"%s.Use *= {self.use_scaling}"


class SynapticMgManipulation(SynapticManipulation):
    """Manipulate the extracellular synaptic magnesium (Mg2+) concentration.\
        This is applied for all synapses between biophysical neurons."""

    title: ClassVar[str] = "Demo: Synaptic Mg2+ Concentration Manipulation"

    magnesium_value: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=2.4, 
        title="Extracellular Magnesium Concentration",
        description="Extracellular calcium concentration in millimoles (mM)", 
        units="mM"
    )
    
    def _get_override_name(self) -> str:
        return "Mg"

    def _get_synapse_configure(self) -> str:
        return f"%%s.mg = {self.magnesium_value}"
