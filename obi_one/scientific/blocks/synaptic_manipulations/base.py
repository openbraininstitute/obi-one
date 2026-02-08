from abc import ABC

from pydantic import Field, PrivateAttr

from obi_one.core.block import Block
from obi_one.scientific.blocks.timestamps import SingleTimestamp
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)
from obi_one.scientific.unions.unions_timestamps import (
    TimestampsReference,
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

    def config(self, default_node_set: str = "All") -> dict:
        self._default_node_set = default_node_set
        return self._sonata_manipulations_list()

    def _sonata_manipulations_list(self) -> dict:
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


class GlobalVariableInterNeuronSetSynapticManipulation(InterNeuronSetSynapticManipulation, ABC):
    def _get_synapse_configure(self) -> str:
        pass

    def _sonata_manipulations_list(self) -> dict:
        manipulation = super()._sonata_manipulations_list()[0]
        manipulation["synapse_configure"] = self._get_synapse_configure()

        return [manipulation]


class ModSpecificVariableInterNeuronSetSynapticManipulation(
    InterNeuronSetSynapticManipulation, ABC
):
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
