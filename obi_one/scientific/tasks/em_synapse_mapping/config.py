import logging
from enum import StrEnum
from typing import ClassVar

from entitysdk.types import EntityType, TaskActivityType, TaskConfigType
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"


class EMSynapseMappingScanConfig(ScanConfig):
    """Map location of afferent synapses from EM onto a spiny morphology."""

    name: ClassVar[str] = "Map synapse locations"

    json_schema_extra_additions: ClassVar[dict] = {
        "ui_enabled": True,
        "group_order": [
            BlockGroup.SETUP_BLOCK_GROUP,
        ],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.em_synapse_mapping__campaign
    )
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.em_synapse_mapping__config_generation
    )

    class Initialize(Block):
        spiny_neuron: CellMorphologyFromID = Field(  # | MEModelFromID
            title="EM skeletonized morphology",
            description="""A neuron morphology with spines obtained from an electron-microscopy
            datasets through the skeletonization task.""",
            json_schema_extra={
                "ui_element": "model_selector_single",
                "entity_query": {
                    "type": EntityType.cell_morphology,
                    "filters": {
                        "cell_morphology_protocol": "ultraliser",
                    },
                },
            },
        )
        edge_population_name: str = Field(
            default="afferent_synapses",
            min_length=1,
            title="Edge population name",
            description="Name of the edge population to write the synapse information into",
            json_schema_extra={
                "ui_element": "string_input",
            },
        )
        node_population_pre: str = Field(
            default="afferent_neurons",
            min_length=1,
            title="Presynaptic node population name",
            description="""Name of the node population to write the information about the
            innervating neurons into""",
            json_schema_extra={
                "ui_element": "string_input",
            },
        )
        node_population_post: str = Field(
            default="biophysical_neuron",
            min_length=1,
            title="Postsynaptic node population name",
            description="""Name of the node population to write the information about the
            synaptome neuron into""",
            json_schema_extra={
                "ui_element": "string_input",
            },
        )

    info: Info = Field(  # type: ignore[]
        title="Info",
        description="Information about ...",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP_BLOCK_GROUP,
            "group_order": 0,
        },
    )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing...",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP_BLOCK_GROUP,
            "group_order": 1,
        },
    )

    @property
    def input_entity_ids(self) -> list[str]:
        return [self.initialize.spiny_neuron.id_str]

    @property
    def campaign_name(self) -> str:
        return self.info.campaign_name

    @property
    def campaign_description(self) -> str:
        return self.info.campaign_description

    @property
    def campaign_task_config_type(self) -> TaskConfigType:
        return TaskConfigType.em_synapse_mapping__campaign

    @property
    def campaign_generation_task_activity_type(self) -> TaskActivityType:
        return TaskActivityType.em_synapse_mapping__config_generation


class EMSynapseMappingSingleConfig(EMSynapseMappingScanConfig, SingleConfigMixin):
    @property
    def single_task_config_type(self) -> TaskConfigType:
        return TaskConfigType.em_synapse_mapping__config
