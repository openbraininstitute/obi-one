from typing import ClassVar

from pydantic import Field, NonNegativeFloat

from obi_one.scientific.blocks.synaptic_manipulations.base import InterNeuronSetSynapticManipulation


class SetSpontaneousMinisRate0HzSynapticManipulation(InterNeuronSetSynapticManipulation):
    """Set spontaneous minis rate to 0Hz. By default, the spontaneous minis rate is set in..."""

    title: ClassVar[str] = "0Hz Spontaneous Minis (Between Neuron Sets)"

    def _sonata_manipulations_list(self) -> dict:
        sonata_config = super()._sonata_manipulations_list()[0]
        sonata_config["spont_minis"] = 0.0

        return [sonata_config]


class SetSpontaneousMinisRateSynapticManipulation(InterNeuronSetSynapticManipulation):
    """Set spontaneous minis rate. By default, the spontaneous minis rate is set in..."""

    title: ClassVar[str] = "Set Spontaneous Minis Rate (Between Neuron Sets)"

    rate: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=1.0,
        title="Spontaneous Minis Rate",
        description="Set the spontaneous minis rate in Hz.",
        json_schema_extra={
            "units": "Hz",
            "ui_element": "float_parameter_sweep",
        },
    )

    def _sonata_manipulations_list(self) -> dict:
        sonata_config = super()._sonata_manipulations_list()[0]
        sonata_config["spont_minis"] = self.rate
        return [sonata_config]
