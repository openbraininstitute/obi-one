from abc import ABC

from pydantic import Field, PrivateAttr

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.timestamps.single import SingleTimestamp
from obi_one.scientific.unions.unions_neuron_sets_2 import (
    ALL_NEURON_SETS_REFERENCE_TYPES,
    ALL_NEURON_SETS_REFERENCE_UNION,
    NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
    resolve_neuron_set_2_ref_to_neuron_set,
)
from obi_one.scientific.unions.unions_timestamps import (
    TimestampsReference,
    resolve_timestamps_ref_to_timestamps_block,
)

_NEURON_SET_DESCRIPTION = (
    "The manipulation is applied to all synapses between"
    " the presynaptic and postsynaptic neuron sets."
)


class InterNeuronSetSynapticManipulation(Block, ABC):
    """Base class for synaptic manipulation applied to all synapses between two neuron sets."""

    presynaptic_neuron_set: ALL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Presynaptic Neuron Set",
        description=_NEURON_SET_DESCRIPTION,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: ALL_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    postsynaptic_neuron_set: ALL_NEURON_SETS_REFERENCE_UNION | None = Field(
        default=None,
        title="Postsynaptic Neuron Set",
        description=_NEURON_SET_DESCRIPTION,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )

    _default_node_set: str = PrivateAttr(default="All")

    def config(self, default_node_set: str = "All") -> dict:
        self._default_node_set = default_node_set
        return self._sonata_manipulations_list()

    def _sonata_manipulations_list(self) -> dict:
        sonata_config = {
            "name": self.block_name,
            "source": resolve_neuron_set_2_ref_to_neuron_set(
                self.presynaptic_neuron_set, self._default_node_set
            ),
            "target": resolve_neuron_set_2_ref_to_neuron_set(
                self.postsynaptic_neuron_set, self._default_node_set
            ),
        }

        return [sonata_config]


class GlobalVariableInterNeuronSetSynapticManipulation(InterNeuronSetSynapticManipulation, ABC):
    """Base class for synaptic manipulations applied to all mechanisms using the variable."""

    def _get_synapse_configure(self) -> str:
        pass

    def _sonata_manipulations_list(self) -> dict:
        manipulation = super()._sonata_manipulations_list()[0]
        manipulation["synapse_configure"] = self._get_synapse_configure()

        return [manipulation]


class ModSpecificVariableInterNeuronSetSynapticManipulation(
    InterNeuronSetSynapticManipulation, ABC
):
    """Base class for synaptic manipulation of a single variable applied to a single mechanism."""

    def _get_synapse_configure(self) -> str:
        pass

    def _get_modoverride_name(self) -> str:
        pass

    def _sonata_manipulations_list(self) -> dict:
        manipulation = super()._sonata_manipulations_list()[0]
        manipulation["synapse_configure"] = self._get_synapse_configure()
        manipulation["modoverride"] = self._get_modoverride_name()

        return [manipulation]


class DelayedInterNeuronSetSynapticManipulation(InterNeuronSetSynapticManipulation, ABC):
    """Base class for synaptic manipulations applied with a delay at different timestamps."""

    _default_timestamps: TimestampsReference = PrivateAttr(default=SingleTimestamp(start_time=0.0))

    timestamps: TimestampsReference | None = Field(
        default=None,
        title="Timestamps",
        description="Timestamps at which the manipulation is applied.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [TimestampsReference.__name__],
        },
    )

    timestamp_offset: float | list[float] | None = Field(
        default=0.0,
        title="Timestamp Offset",
        description="An optional offset of the manipulation relative to each "
        "timestamp in milliseconds (ms).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )


class WeightChangeDelayedInterNeuronSetSynapticManipulation(
    DelayedInterNeuronSetSynapticManipulation, ABC
):
    """Base class for synaptic manipulations with a weight change parameter."""

    _weight: float = PrivateAttr(default=0.0)

    def _sonata_manipulations_list(self) -> list:
        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )

        timestamps = timestamps_block.timestamps()
        n_timestamps = len(timestamps)

        manipulation = super()._sonata_manipulations_list()[0]
        name = manipulation["name"]

        manipulations_list = []
        for t_ind, timestamp in enumerate(timestamps):
            new_manipulation = manipulation.copy()
            new_manipulation["name"] = f"{name}_{t_ind}" if n_timestamps > 1 else name
            new_manipulation["delay"] = timestamp + self.timestamp_offset
            new_manipulation["weight"] = self._weight
            manipulations_list.append(new_manipulation)

        return manipulations_list
