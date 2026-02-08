from typing import ClassVar

from obi_one.scientific.blocks.synaptic_manipulations.base import (
    DelayedInterNeuronSetSynapticManipulation,
)
from obi_one.scientific.unions.unions_timestamps import (
    resolve_timestamps_ref_to_timestamps_block,
)


class DisconnectSynapticManipulation(DelayedInterNeuronSetSynapticManipulation):
    """Disconnect synapses between specified source and target neuron sets."""

    title: ClassVar[str] = "Disconnect Synapses (Between Neuron Sets)"

    def _sonata_manipulations_list(self) -> dict:
        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )

        manipulations_list = []
        for t_ind, timestamp in enumerate(timestamps_block.timestamps()):
            manipulation = super()._sonata_manipulations_list()[0]
            manipulation["name"] = manipulation["name"] + "_" + str(t_ind)
            manipulation["delay"] = timestamp + self.timestamp_offset
            manipulation["weight"] = 0.0
            manipulations_list.append(manipulation)

        return manipulations_list


class ConnectSynapticManipulation(DelayedInterNeuronSetSynapticManipulation):
    """Connect synapses between specified source and target neuron sets."""

    title: ClassVar[str] = "Connect Synapses (Between Neuron Sets)"

    def _sonata_manipulations_list(self) -> dict:
        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )

        manipulations_list = []
        for t_ind, timestamp in enumerate(timestamps_block.timestamps()):
            manipulation = super()._sonata_manipulations_list()[0]
            manipulation["name"] = manipulation["name"] + "_" + str(t_ind)
            manipulation["delay"] = timestamp + self.timestamp_offset
            manipulation["weight"] = 1.0
            manipulations_list.append(manipulation)

        return manipulations_list
