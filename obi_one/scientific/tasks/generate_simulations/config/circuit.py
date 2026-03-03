import logging
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.circuit_from_id import (
    CircuitFromID,
)
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BlockGroup,
    SimulationScanConfig,
    SimulationSingleConfigMixin,
)
from obi_one.scientific.unions.unions_manipulations import (
    SynapticManipulationsReference,
    SynapticManipulationsUnion,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    SimulationNeuronSetUnion,
)
from obi_one.scientific.unions.unions_stimuli import (
    CircuitStimulusUnion,
    StimulusReference,
)

L = logging.getLogger(__name__)

CircuitDiscriminator = Annotated[Circuit | CircuitFromID, Field(discriminator="type")]


class CircuitSimulationScanConfig(SimulationScanConfig):
    """CircuitSimulationScanConfig."""

    single_coord_class_name: ClassVar[str] = "CircuitSimulationSingleConfig"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    neuron_sets: dict[str, SimulationNeuronSetUnion] = Field(
        default_factory=dict,
        description="Neuron sets for the simulation.",
        json_schema_extra={
            "ui_element": "block_dictionary",
            "reference_type": NeuronSetReference.__name__,
            "singular_name": "Neuron Set",
            "group": BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            "group_order": 0,
        },
    )
    synaptic_manipulations: dict[str, SynapticManipulationsUnion] = Field(
        default_factory=dict,
        description="Synaptic manipulations for the simulation.",
        json_schema_extra={
            "ui_element": "block_dictionary",
            "reference_type": SynapticManipulationsReference.__name__,
            "singular_name": "Synaptic Manipulation",
            "group": BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            "group_order": 1,
        },
    )

    class Initialize(SimulationScanConfig.Initialize):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit",
            description="Circuit to simulate.",
            json_schema_extra={"ui_element": "model_identifier"},
        )
        node_set: NeuronSetReference | None = Field(
            default=None,
            title="Neuron Set",
            description="Neuron set to simulate.",
            json_schema_extra={
                "ui_element": "reference",
                "reference_type": NeuronSetReference.__name__,
            },
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the simulation.",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP_BLOCK_GROUP,
            "group_order": 1,
        },
    )

    stimuli: dict[str, CircuitStimulusUnion] = Field(
        default_factory=dict,
        title="Stimuli",
        description="Stimuli for the simulation.",
        json_schema_extra={
            "ui_element": "block_dictionary",
            "reference_type": StimulusReference.__name__,
            "singular_name": "Stimulus",
            "group": BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            "group_order": 0,
        },
    )


class CircuitSimulationSingleConfig(
    CircuitSimulationScanConfig, SingleConfigMixin, SimulationSingleConfigMixin
):
    """Only allows single values."""
