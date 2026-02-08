import logging
from enum import StrEnum
from typing import Annotated, ClassVar

import entitysdk
from pydantic import ConfigDict, Field

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.circuit_from_id import (
    CircuitFromID,
    MEModelWithSynapsesCircuitFromID,
)
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.memodel_circuit import MEModelCircuit, MEModelWithSynapsesCircuit
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    SimulationNeuronSetUnion,
)
from obi_one.scientific.unions.unions_timestamps import (
    TimestampsReference,
    TimestampsUnion,
)

L = logging.getLogger(__name__)

import logging

from entitysdk import Client

from obi_one.core.task import Task
from obi_one.scientific.tasks.generate_simulation_configs import CircuitDiscriminator

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


class ProcessSimulationCampaignScanConfig(ScanConfig):
    """ProcessSimulationCampaignScanConfig."""

    single_coord_class_name: ClassVar[str] = "ProcessSimulationCampaignSingleConfig"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"

    campaign: entitysdk.models.SimulationCampaign = None

    model_config = ConfigDict(
        json_schema_extra={
            "ui_enabled": True,
            "group_order": [
                BlockGroup.SETUP_BLOCK_GROUP,
                BlockGroup.CIRUIT_COMPONENTS_BLOCK_GROUP,
                BlockGroup.EVENTS_GROUP,
            ],
            "default_block_reference_labels": {
                NeuronSetReference.__name__: DEFAULT_NODE_SET_NAME,
                TimestampsReference.__name__: DEFAULT_TIMESTAMPS_NAME,
            },
        }
    )

    class Initialize(Block):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit",
            description="Circuit to simulate.",
            json_schema_extra={"ui_element": "model_identifier"},
        )

    info: Info = Field(  # type: ignore[]
        title="Info",
        description="Information about the simulation campaign.",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP_BLOCK_GROUP,
            "group_order": 0,
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

    # windows: dict[str, WindowUnion] = Field(
    #     default_factory=dict,
    #     description="",
    #     json_schema_extra={
    #         "ui_element": "block_dictionary",
    #         "reference_type": RecordingReference.__name__,
    #         "singular_name": "Recording",
    #         "group": BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
    #         "group_order": 1,
    #     },
    # )

    # features: dict[str, FeaturesUnion] = Field(
    #     default_factory=dict,
    #     description="",
    #     json_schema_extra={
    #         "ui_element": "block_dictionary",
    #         "reference_type": RecordingReference.__name__,
    #         "singular_name": "Recording",
    #         "group": BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
    #         "group_order": 1,
    #     },
    # )

    neuron_sets: dict[str, SimulationNeuronSetUnion] = Field(
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

    timestamps: dict[str, TimestampsUnion] = Field(
        default_factory=dict,
        title="Timestamps",
        description="Timestamps for the simulation.",
        json_schema_extra={
            "ui_element": "block_dictionary",
            "reference_type": TimestampsReference.__name__,
            "singular_name": "Timestamps",
            "group": BlockGroup.EVENTS_GROUP,
            "group_order": 0,
        },
    )

    # simulations_filter: str | None = Field(
    #     default=None,
    #     title="Simulations Filter",
    #     description=(
    #         "Filter to select a subset of simulations to process. Should be a valid Python expression that can be evaluated with the variables 'simulation_id' and 'simulation_metadata'. For example, 'simulation_metadata[\"temperature\"] > 30' would select simulations where the temperature metadata is greater than 30."
    #     ),
    #     json_schema_extra={
    #         "ui_element": "text_input",
    #         "group": BlockGroup.SETUP_BLOCK_GROUP,
    #         "group_order": 2,
    #     },
    # )


class ProcessSimulationCampaignSingleConfig(ProcessSimulationCampaignScanConfig, SingleConfigMixin):
    """Only allows single values."""


class CircuitExtractionTask(Task):
    config: ProcessSimulationCampaignSingleConfig

    def execute(
        self,
        *,
        db_client: Client = None,
        entity_cache: bool = False,
        execution_activity_id: str | None = None,
    ) -> str | None:
        pass
