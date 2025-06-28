from abc import ABC, abstractmethod
from obi_one.core.block import Block
from pydantic import NonNegativeFloat
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


class SynapticUseManipulation(SynapticManipulation):
    """Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."""

    title: ClassVar[str] = "Synaptic Use Manipulation"

    use_scaling: NonNegativeFloat | list[NonNegativeFloat] = 0.7050728631217412

    def _get_override_name(self) -> str:
        return "ach_use"

    def _get_synapse_configure(self) -> str:
        return f"%s.Use *= {self.use_scaling}"


class SynapticMgManipulation(SynapticManipulation):
    """Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."""

    title: ClassVar[str] = "Synaptic Mg2+ Concentration Manipulation"

    magnesium_value: NonNegativeFloat | list[NonNegativeFloat] = 2.4
    
    def _get_override_name(self) -> str:
        return "Mg"

    def _get_synapse_configure(self) -> str:
        return f"%%s.mg = {self.magnesium_value}"
