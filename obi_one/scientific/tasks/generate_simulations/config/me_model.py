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
    DEFAULT_NODE_SET_NAME,
    DEFAULT_TIMESTAMPS_NAME,
    SimulationScanConfig,
    SimulationSingleConfigMixin,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
)
from obi_one.scientific.unions.unions_stimuli import (
    MEModelStimulusUnion,
    StimulusReference,
)
from obi_one.scientific.unions.unions_timestamps import (
    TimestampsReference,
)

L = logging.getLogger(__name__)


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


class MEModelSimulationScanConfig(SimulationScanConfig):
    """MEModelSimulationScanConfig."""

    single_coord_class_name: ClassVar[str] = "MEModelSimulationSingleConfig"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    class Initialize(SimulationScanConfig.Initialize):
        circuit: MEModelDiscriminator | list[MEModelDiscriminator] = Field(
            title="ME Model",
            description="ME Model to simulate.",
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

    stimuli: dict[str, MEModelStimulusUnion] = Field(
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

    json_schema_extra_additions: ClassVar[dict] = {
        "ui_enabled": True,
        "group_order": [
            BlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            BlockGroup.EVENTS_GROUP,
        ],
        "default_block_reference_labels": {
            NeuronSetReference.__name__: DEFAULT_NODE_SET_NAME,
            TimestampsReference.__name__: DEFAULT_TIMESTAMPS_NAME,
        },
    }


class MEModelSimulationSingleConfig(
    MEModelSimulationScanConfig, SingleConfigMixin, SimulationSingleConfigMixin
):
    """Only allows single values."""
