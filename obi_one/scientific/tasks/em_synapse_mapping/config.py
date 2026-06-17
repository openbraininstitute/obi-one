import logging
from enum import StrEnum
from typing import ClassVar, Self

from entitysdk.client import Client
from entitysdk.models import Entity
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import Field, model_validator

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.schema import AcceptedInputTypes, SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.named_tuple_from_id import EMSynapseMappingInputNamedTuple
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    SETUP_BLOCK_GROUP = "Setup"
    ADVANCED_BLOCK_GROUP = "Advanced"


class AdvancedEMSynapseMappingOptions(Block):
    custom_physical_edge_population_name: str = Field(
        title="Custom physical edge population name",
        description="Custom name for the population of connections between neurons in the circuit."
        " 'physical_connections' is used if not specified.",
        default="",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
        },
    )
    custom_virtual_edge_population_name: str = Field(
        title="Custom virtual edge population name",
        description="Custom name for the population of connections from virtual neurons."
        " 'virtual_afferents' is used if not specified.",
        default="",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
        },
    )
    custom_biophysical_node_population: str = Field(
        title="Custom biophysical node population name",
        description="Custom name for the population of physical neurons in the circuit."
        " 'biophysical_neurons' is used if not specified.",
        default="",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
        },
    )
    custom_virtual_node_population: str = Field(
        title="Custom virtual node population name",
        description="Custom name for the population of external presynaptic neurons."
        " 'virtual_afferent_neurons' is used if not specified.",
        default="",
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
            BlockGroup.ADVANCED_BLOCK_GROUP,
        ],
    }

    _campaign_task_config_type: ClassVar[TaskConfigType] = (
        TaskConfigType.em_synapse_mapping__campaign
    )
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.em_synapse_mapping__config_generation
    )

    def input_entities(self, db_client: Client) -> list[Entity]:
        if isinstance(self.initialize.neurons, EMSynapseMappingInputNamedTuple):
            return [n.entity(db_client=db_client) for n in self.initialize.neurons.elements]
        if isinstance(self.initialize.neurons, list):
            # make sure that there are no duplicate in the returned list of entities
            to_return = []
            to_return_ids = []
            for input_tuple in self.initialize.neurons:
                for n in input_tuple.elements:
                    if n.id_str not in to_return_ids:
                        to_return_ids.append(n.id_str)
                        to_return.append(n.entity(db_client=db_client))
            return to_return
        msg = (
            "Invalid type for neurons. "
            "Expected EMSynapseMappingInputNamedTuple or list of EMSynapseMappingInputNamedTuple."
        )
        raise ValueError(msg)

    class Initialize(Block):
        # We use a named tuple instead of a list to avoid getting it taken as scan dimensions
        # in the scan config. list[named tuple] for scanning over different sets of neurons.
        neurons: EMSynapseMappingInputNamedTuple | list[EMSynapseMappingInputNamedTuple] = Field(
            title="Neurons",
            description="Neurons to include in the circuit (>= 1).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER_MULTIPLE,
                SchemaKey.ACCEPTED_INPUT_TYPES: [
                    AcceptedInputTypes.CELL_MORPHOLOGY_FROM_ID,
                    AcceptedInputTypes.ME_MODEL_FROM_ID,
                ],
            },
        )

        @model_validator(mode="after")
        def check_neuron_structure(self) -> Self:
            if isinstance(self.neurons, list):
                if len(self.neurons) < 1:
                    msg = (
                        "At least one set of neurons must be provided in "
                        "EM Synapse Mapping Scan Config."
                    )
                    raise OBIONEError(msg)

                tuple_names = [input_tuple.name for input_tuple in self.neurons]
                if len(tuple_names) != len(set(tuple_names)):
                    msg = (
                        "All named tuples in the list of neurons must have unique names "
                        "in EM Synapse Mapping Scan Config."
                    )
                    raise OBIONEError(msg)
            return self

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
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.ADVANCED_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 2,
        },
    )


class EMSynapseMappingSingleConfig(EMSynapseMappingScanConfig, SingleConfigMixin):
    _single_task_config_type: ClassVar[TaskConfigType] = TaskConfigType.em_synapse_mapping__config
    _single_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.em_synapse_mapping__execution
    )

    class Initialize(EMSynapseMappingScanConfig.Initialize):
        neurons: "EMSynapseMappingInputNamedTuple"

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the EM Synaptome.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
