import logging
from enum import StrEnum
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.circuit_from_id import (
    CircuitFromID,
    MEModelWithSynapsesCircuitFromID,
)
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.memodel_circuit import MEModelCircuit, MEModelWithSynapsesCircuit
from obi_one.scientific.tasks.generate_simulations.config.base import (
    SimulationScanConfig,
    SimulationSingleConfigMixin,
)
from obi_one.scientific.tasks.generate_simulations.config.circuit import CircuitSimulationScanConfig
from obi_one.scientific.unions.unions_neuron_sets import (
    MEModelWithSynapsesNeuronSetUnion,
    NeuronSetReference,
)

L = logging.getLogger(__name__)


DEFAULT_NODE_SET_NAME = "Default: All Biophysical Neurons"
DEFAULT_TIMESTAMPS_NAME = "Default: Simulation Start (0 ms)"


class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"
    STIMULI_RECORDINGS_BLOCK_GROUP = "Stimuli & Recordings"
    CIRUIT_COMPONENTS_BLOCK_GROUP = "Circuit Components"
    EVENTS_GROUP = "Events"
    CIRCUIT_MANIPULATIONS_GROUP = "Circuit Manipulations"


CircuitDiscriminator = Annotated[Circuit | CircuitFromID, Field(discriminator="type")]
MEModelDiscriminator = Annotated[MEModelCircuit | MEModelFromID, Field(discriminator="type")]
MEModelWithSynapsesCircuitDiscriminator = Annotated[
    MEModelWithSynapsesCircuit | MEModelWithSynapsesCircuitFromID, Field(discriminator="type")
]

TARGET_SIMULATOR = "NEURON"
SONATA_VERSION = 2.4


class MEModelWithSynapsesCircuitSimulationScanConfig(CircuitSimulationScanConfig):
    """MEModelWithSynapsesCircuitSimulationScanConfig."""

    single_coord_class_name: ClassVar[str] = "MEModelWithSynapsesCircuitSimulationSingleConfig"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    neuron_sets: dict[str, MEModelWithSynapsesNeuronSetUnion] = Field(
        default_factory=dict,
        description="Neuron sets for the simulation.",
        json_schema_extra={
            "ui_element": "block_dictionary",
            "reference_type": NeuronSetReference.__name__,
            "singular_name": "Neuron Set",
            "group": BlockGroup.CIRUIT_COMPONENTS_BLOCK_GROUP,
            "group_order": 0,
        },
    )

    class Initialize(SimulationScanConfig.Initialize):
        circuit: (
            MEModelWithSynapsesCircuitDiscriminator | list[MEModelWithSynapsesCircuitDiscriminator]
        ) = Field(
            title="MEModel With Synapses",
            description="MEModel with synapses to simulate.",
            json_schema_extra={"ui_element": "model_identifier"},
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


class MEModelWithSynapsesCircuitSimulationSingleConfig(
    MEModelWithSynapsesCircuitSimulationScanConfig, SingleConfigMixin, SimulationSingleConfigMixin
):
    """Only allows single values."""
