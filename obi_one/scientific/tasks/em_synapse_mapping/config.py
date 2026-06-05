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
        physical_edge_population_name: str = Field(
            title="Physical edge population name",
            description="Edge population for connections between neurons in the set.",
            default="physical_connections",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
            },
        )
        virtual_edge_population_name: str = Field(
            title="Virtual edge population name",
            description="Edge population for connections from virtual neurons.",
            default="virtual_afferents",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
            },
        )
        biophysical_node_population: str = Field(
            title="Biophysical node population name",
            description="Node population for the physical neurons in the circuit.",
            default="biophysical_neurons",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
            },
        )
        virtual_node_population: str = Field(
            title="Virtual node population name",
            description="Node population for external presynaptic neurons.",
            default="virtual_afferent_neurons",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
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
