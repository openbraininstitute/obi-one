from abc import ABC
from typing import ClassVar

from pydantic import Field, NonNegativeFloat, PrivateAttr

from obi_one.core.block import Block

from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)

class NewSynapticManipulation(Block, ABC):

    # Should this be a SingleTimestamp?
    timestamp: NonNegativeFloat | list[NonNegativeFloat] = Field(
        ui_element="float_parameter_sweep",
        default=0.0,
        title="Timestamp",
        description="Time at which synaptic manipulation occurs in milliseconds (ms).",
        units="ms",
    )

    source_neuron_set: NeuronSetReference | None = Field(
        default=None,
        ui_element="reference",
        reference_type=NeuronSetReference.__name__,
        title="Neuron Set (Source)",
        description="Source neuron set to simulate",
        supports_virtual=True,
    )

    targeted_neuron_set: NeuronSetReference | None = Field(
        default=None,
        ui_element="reference",
        reference_type=NeuronSetReference.__name__,
        title="Neuron Set (Target)",
        description="Target neuron set to simulate",
        supports_virtual=False,
    )

    _default_node_set: str = PrivateAttr(default="All")

    @staticmethod
    def _get_override_name() -> str:
        pass

    def config(self, default_node_set: str = "All") -> dict:
        self._default_node_set = default_node_set
        return self._generate_config()

    def _generate_config(self) -> dict:
        sonata_config = {
            "name": self.block_name,
            "source": resolve_neuron_set_ref_to_node_set(
                self.source_neuron_set, self._default_node_set
            ),
            "target": resolve_neuron_set_ref_to_node_set(
                self.targeted_neuron_set, self._default_node_set
            ),
            "delay": self.timestamp,
        }

        return sonata_config

class DisconnectSynapticManipulation(NewSynapticManipulation):
    """Disconnect synapses between specified source and target neuron sets."""

    title: ClassVar[str] = "Disconnect Synapses"

    def _generate_config(self) -> dict:
        sonata_config = super()._generate_config()
        sonata_config["weight"] = 0.0

        return sonata_config
    
class ConnectSynapticManipulation(NewSynapticManipulation):
    """Connect synapses between specified source and target neuron sets."""

    title: ClassVar[str] = "Connect Synapses"

    def _generate_config(self) -> dict:
        sonata_config = super()._generate_config()
        sonata_config["weight"] = 0.0

        return sonata_config
    

class SynapticManipulation(Block, ABC):
    @staticmethod
    def _get_override_name() -> str:
        pass

    def config(self, default_node_set: str = "All") -> dict:
        self._default_node_set = default_node_set
        return self._generate_config()

    def _generate_config(self) -> dict:
        sonata_config = {
            "name": self._get_override_name(),
            "source": "All",
            "target": "All",
            "synapse_configure": self._get_synapse_configure(),
        }

        return sonata_config


class GlobalSynapticManipulation(SynapticManipulation):
    def _get_modoverride_name(self) -> str:
        pass

    def _generate_config(self) -> dict:
        sonata_config = {
            "name": self._get_override_name(),
            "source": "All",
            "target": "All",
            "synapse_configure": self._get_synapse_configure(),
            "modoverride": self._get_modoverride_name(),
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
        ui_element="float_parameter_sweep",
        default=0.7050728631217412,
        title="Scale U_SE (ACh)",
        description="Scale the U_SE (ACh) parameter of the Tsodyks-Markram synaptic model.",
    )

    @staticmethod
    def _get_override_name() -> str:
        return "ach_use"

    def _get_synapse_configure(self) -> str:
        return f"%s.Use *= {self.use_scaling}"


class SynapticMgManipulation(GlobalSynapticManipulation):
    """Manipulate the extracellular synaptic magnesium (Mg2+) concentration.

    This is applied for all synapses between biophysical neurons.
    """

    title: ClassVar[str] = "Demo: Synaptic Mg2+ Concentration Manipulation"

    magnesium_value: NonNegativeFloat | list[NonNegativeFloat] = Field(
        ui_element="float_parameter_sweep",
        default=2.4,
        title="Extracellular Magnesium Concentration",
        description="Extracellular magnesium concentration in millimoles (mM).",
        units="mM",
    )

    @staticmethod
    def _get_override_name() -> str:
        return "Mg"

    def _get_synapse_configure(self) -> str:
        return f"mg = {self.magnesium_value}"

    @staticmethod
    def _get_modoverride_name() -> str:
        return "GluSynapse"
