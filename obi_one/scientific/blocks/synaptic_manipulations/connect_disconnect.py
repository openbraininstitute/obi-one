from typing import ClassVar

from pydantic import PrivateAttr

from obi_one.scientific.blocks.synaptic_manipulations.base import (
    WeightChangeDelayedInterNeuronSetSynapticManipulation,
)


class DisconnectSynapticManipulation(WeightChangeDelayedInterNeuronSetSynapticManipulation):
    """Disconnect synapses between specified source and target neuron sets."""

    title: ClassVar[str] = "Disconnect Synapses"

    _weight: float = PrivateAttr(default=0.0)


class ConnectSynapticManipulation(WeightChangeDelayedInterNeuronSetSynapticManipulation):
    """Connect synapses between specified source and target neuron sets."""

    title: ClassVar[str] = "Connect Synapses"

    _weight: float = PrivateAttr(default=1.0)
