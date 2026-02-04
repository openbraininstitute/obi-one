from abc import ABC
from typing import ClassVar

from pydantic import Field, NonNegativeFloat, PrivateAttr

from obi_one.core.block import Block
from obi_one.scientific.blocks.timestamps import SingleTimestamp
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)
from obi_one.scientific.unions.unions_timestamps import (
    TimestampsReference,
    resolve_timestamps_ref_to_timestamps_block,
)


class InterNeuronSetSynapticManipulation(Block, ABC):
    source_neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Source)",
        description="Source neuron set to simulate",
        json_schema_extra={
            "supports_virtual": True,
            "ui_element": "reference",
            "reference_type": NeuronSetReference.__name__,
        },
    )

    target_neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Target neuron set to simulate",
        json_schema_extra={
            "supports_virtual": False,
            "ui_element": "reference",
            "reference_type": NeuronSetReference.__name__,
        },
    )

    _default_node_set: str = PrivateAttr(default="All")

    @staticmethod
    def _get_override_name() -> str:
        pass

    def config(self, default_node_set: str = "All") -> dict:
        self._default_node_set = default_node_set
        return self._generate_sonata_manipulations_list()

    def _generate_sonata_manipulations_list(self) -> dict:
        sonata_config = {
            "name": self.block_name,
            "source": resolve_neuron_set_ref_to_node_set(
                self.source_neuron_set, self._default_node_set
            ),
            "target": resolve_neuron_set_ref_to_node_set(
                self.target_neuron_set, self._default_node_set
            ),
        }

        return [sonata_config]


class DelayedInterNeuronSetSynapticManipulation(InterNeuronSetSynapticManipulation):
    """Base class for synaptic manipulations with a delay parameter."""

    _default_timestamps: TimestampsReference = PrivateAttr(default=SingleTimestamp(start_time=0.0))

    timestamps: TimestampsReference | None = Field(
        default=None,
        title="Timestamps",
        description="Timestamps at which the stimulus is applied.",
        json_schema_extra={
            "ui_element": "reference",
            "reference_type": TimestampsReference.__name__,
        },
    )

    timestamp_offset: float | list[float] | None = Field(
        default=0.0,
        title="Timestamp Offset",
        description="The offset of the stimulus relative to each timestamp in milliseconds (ms).",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "ms",
        },
    )


class DisconnectSynapticManipulation(DelayedInterNeuronSetSynapticManipulation):
    """Disconnect synapses between specified source and target neuron sets."""

    title: ClassVar[str] = "Disconnect Synapses (Between Neuron Sets)"

    def _generate_sonata_manipulations_list(self) -> dict:
        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )

        manipulations_list = []
        for t_ind, timestamp in enumerate(timestamps_block.timestamps()):
            manipulation_dict = super()._generate_sonata_manipulations_list()[0]
            manipulation_dict["name"] = manipulation_dict["name"] + "_" + str(t_ind)
            manipulation_dict["delay"] = timestamp + self.timestamp_offset
            manipulation_dict["weight"] = 0.0
            manipulations_list.append(manipulation_dict)

        return manipulations_list


class ConnectSynapticManipulation(DelayedInterNeuronSetSynapticManipulation):
    """Connect synapses between specified source and target neuron sets."""

    title: ClassVar[str] = "Connect Synapses (Between Neuron Sets)"

    def _generate_sonata_manipulations_list(self) -> dict:
        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )

        manipulations_list = []
        for t_ind, timestamp in enumerate(timestamps_block.timestamps()):
            manipulation_dict = super()._generate_sonata_manipulations_list()[0]
            manipulation_dict["name"] = manipulation_dict["name"] + "_" + str(t_ind)
            manipulation_dict["delay"] = timestamp + self.timestamp_offset
            manipulation_dict["weight"] = 1.0
            manipulations_list.append(manipulation_dict)

        return manipulations_list


class SetSpontaneousMinisRate0HzSynapticManipulation(InterNeuronSetSynapticManipulation):
    """Set spontaneous minis rate to 0Hz. By default, the spontaneous minis rate is set in..."""

    title: ClassVar[str] = "0Hz Spontaneous Minis (Between Neuron Sets)"

    def _generate_sonata_manipulations_list(self) -> dict:
        sonata_config = super()._generate_sonata_manipulations_list()[0]
        sonata_config["spont_minis"] = 0.0

        return [sonata_config]


class SetSpontaneousMinisRateSynapticManipulation(InterNeuronSetSynapticManipulation):
    """Set spontaneous minis rate. By default, the spontaneous minis rate is set in..."""

    title: ClassVar[str] = "Set Spontaneous Minis Rate (Between Neuron Sets)"

    rate: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        title="Spontaneous Minis Rate",
        description="Set the spontaneous minis rate in Hz.",
        json_schema_extra={
            "units": "Hz",
            "ui_element": "float_parameter_sweep",
        },
    )

    def _generate_sonata_manipulations_list(self) -> dict:
        sonata_config = super()._generate_sonata_manipulations_list()[0]
        sonata_config["spont_minis"] = self.rate
        return [sonata_config]
