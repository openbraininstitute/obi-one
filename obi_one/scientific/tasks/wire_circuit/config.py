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
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig

L = logging.getLogger(__name__)

class BlockGroup(StrEnum):
    SETUP_BLOCK_GROUP = "Setup"

class WireStructuralCircuitScanConfig(InfoScanConfig):
    """Create structural SONATA circuit from adjacency matrix"""

    single_coord_class_name: ClassVar[str] = "WireStructuralCircuitSingleConfig"
    name: ClassVar[str] = "Create structural SONATA circuit"
    description: ClassVar[str] = "Campaign for the creation of a structural SONATA circuit"

    def input_entities(self, db_client: Client) -> list[Entity]:
        return [self.initialize.circuit.entity(db_client=db_client)]
    
    class Initialize(Block):
        # We use a tuple instead of a list to avoid getting it taken as scan dimensions
        # in the scan config.
        circuit: CircuitFromID = Field(
            title="Circuit",
            description="Circuit to create a SONATA representation of",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
            },
        )
        edge_population_name: str = Field(
            title="Edge population name",
            description="Edge population for connections between neurons in the circuit.",
            default="default",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
            },
        )
        node_population_name: str = Field(
            title="Biophysical node population name",
            description="Node population for the physical neurons in the circuit.",
            default="biophysical_neurons",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
            },
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the Circuit.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

class WireStructuralCircuitSingleConfig(WireStructuralCircuitScanConfig, SingleConfigMixin):
    pass
