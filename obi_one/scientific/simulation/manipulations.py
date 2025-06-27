from abc import ABC, abstractmethod
from obi_one.core.block import Block


class SynapticManipulation(Block, ABC):

    @abstractmethod
    def _get_override_name(self) -> str:
        pass

    def _generate_config(self) -> dict:
        sonata_config = {
            "name": self._get_override_name(),
            "source": "All",
            "target": "All",
            "synapse_configure": self._get_synapse_configure(),
        }

        return sonata_config


class SynapticUseManipulation(SynapticManipulation):

    use_scaling: float | list[float] = 0.7050728631217412

    def _get_override_name(self) -> str:
        return "ach_use"

    def _get_synapse_configure(self) -> str:
        return f"%s.Use *= {self.use_scaling}"


class SynapticMgManipulation(SynapticManipulation):

    magnesium_value: float | list[float] = 2.4
    
    def _get_override_name(self) -> str:
        return "Mg"

    def _get_synapse_configure(self) -> str:
        return f"%%s.mg = {self.magnesium_value}"
