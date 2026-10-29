from typing import ClassVar

from pydantic import Field, NonNegativeFloat, PrivateAttr

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.synaptic_manipulations.base import (
    WeightChangeDelayedInterNeuronSetSynapticManipulation,
)


class DisconnectSynapticManipulation(WeightChangeDelayedInterNeuronSetSynapticManipulation):
    """Disconnect all synapses between specified source and target neuron sets."""

    title: ClassVar[str] = "Disconnect synapses"

    _weight: float = PrivateAttr(default=0.0)


class ConnectSynapticManipulation(WeightChangeDelayedInterNeuronSetSynapticManipulation):
    """Connect all synapses between specified source and target neuron sets."""

    title: ClassVar[str] = "Connect synapses"

    _weight: float = PrivateAttr(default=1.0)


class ScaleWeightSynapticManipulation(WeightChangeDelayedInterNeuronSetSynapticManipulation):
    """Scale the weight of all synapses between specified source and target neuron sets."""

    title: ClassVar[str] = "Scale synaptic weight"

    # Brian2 circuits carry inhibition in the weight's sign, which a negative factor would flip.
    weight_scaling: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=1.0,
        title="Weight scaling",
        description="Factor on the weight of each synapse as the circuit defines it, so factors"
        " do not compound: 0 disconnects the synapses and 1 restores their weight.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )

    def _get_weight(self) -> float:
        return self.weight_scaling  # ty:ignore[invalid-return-type]
