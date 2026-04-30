import logging
from enum import StrEnum
from typing import ClassVar

from entitysdk.client import Client
from entitysdk.models import Entity
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.tuple import NamedTuple
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    SETUP_BLOCK_GROUP = "Setup"


class EMSynapseMappingInputNamedTuple(NamedTuple):
    elements: tuple[CellMorphologyFromID | MEModelFromID, ...] = Field(min_length=1)


class AdvancedEMSynapseMappingOptions(StrEnum):
    custom_physical_edge_population_name: str = Field(
        title="Physical edge population name",
        description="Edge population for connections between neurons in the set.",
        default="physical_connections",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
        },
    )
    custom_virtual_edge_population_name: str = Field(
        title="Virtual edge population name",
        description="Edge population for connections from virtual neurons.",
        default="virtual_afferents",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
        },
    )
    custom_biophysical_node_population: str = Field(
        title="Biophysical node population name",
        description="Node population for the physical neurons in the circuit.",
        default="biophysical_neurons",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
        },
    )
    custom_virtual_node_population: str = Field(
        title="Virtual node population name",
        description="Node population for external presynaptic neurons.",
        default="virtual_afferent_neurons",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
        },
    )


class EMSynapseMappingScanConfig(InfoScanConfig):
    """Map location of afferent synapses from EM onto one or more spiny morphologies."""

    single_coord_class_name: ClassVar[str] = "EMSynapseMappingSingleConfig"
    name: ClassVar[str] = "Map synapse locations"
    description: ClassVar[str] = "EM synapse mapping campaign"

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP_BLOCK_GROUP,
        ],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.em_synapse_mapping__campaign
    )
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.em_synapse_mapping__config_generation
    )

    def input_entities(self, db_client: Client) -> list[Entity]:
        return [n.entity(db_client=db_client) for n in self.initialize.neurons]

    class Initialize(Block):
        # We use a tuple instead of a list to avoid getting it taken as scan dimensions
        # in the scan config.
        neurons: EMSynapseMappingInputNamedTuple | list[EMSynapseMappingInputNamedTuple] = Field(
            title="Neurons",
            description="Neurons to include in the circuit (>= 1).",
            min_length=1,
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER_MULTIPLE,
            },
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the EM Synaptome.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    advanced_options: AdvancedEMSynapseMappingOptions = Field(
        title="Advanced",
        description="Advanced options for EM synapse mapping.",
        default=AdvancedEMSynapseMappingOptions.DEFAULT,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.ENUM_DROPDOWN,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 2,
        },
    )


class EMSynapseMappingSingleConfig(EMSynapseMappingScanConfig, SingleConfigMixin):
    _single_task_config_type: ClassVar[TaskConfigType] = TaskConfigType.em_synapse_mapping__config
    _single_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.em_synapse_mapping__execution
    )
