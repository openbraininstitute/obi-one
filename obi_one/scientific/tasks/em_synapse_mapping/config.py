import logging
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from entitysdk.client import Client
from entitysdk.models import Entity
from entitysdk.types import EntityType, TaskActivityType, TaskConfigType
from pydantic import Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    SETUP_BLOCK_GROUP = "Setup"


class EMSynapseMappingScanConfig(InfoScanConfig):
    """Map location of afferent synapses from EM onto a spiny morphology."""

    name: ClassVar[str] = "Map synapse locations"

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
        return [self.initialize.spiny_neuron.entity(db_client=db_client)]

    class Initialize(Block):
        spiny_neuron: CellMorphologyFromID = Field(  # | MEModelFromID
            title="EM skeletonized morphology",
            description="""A neuron morphology with spines obtained from an electron-microscopy
            datasets through the skeletonization task.""",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
                SchemaKey.ENTITY_QUERY: {
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
                SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
            },
        )
        node_population_pre: str = Field(
            default="afferent_neurons",
            min_length=1,
            title="Presynaptic node population name",
            description="""Name of the node population to write the information about the
            innervating neurons into""",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
            },
        )
        node_population_post: str = Field(
            default="biophysical_neuron",
            min_length=1,
            title="Postsynaptic node population name",
            description="""Name of the node population to write the information about the
            synaptome neuron into""",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
            },
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing...",
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


class NeuronEntry(OBIBaseModel):
    """A single neuron entry for the multi-neuron synapse mapping task."""

    neuron: CellMorphologyFromID | MEModelFromID = Field(
        title="EM skeletonized morphology",
        description=("A spiny neuron morphology from an EM dataset."),
    )
    pt_root_id: int | None = Field(
        title="Neuron identifier within the EM dense reconstruction dataset.",
        description="If not provided, it will be inferred from the provenance of the morphology.",
        default=None,
    )


class EMSynapseMappingMultipleConfig(OBIBaseModel):
    """Config for multi-neuron synapse mapping."""

    name: ClassVar[str] = "Map synapse locations (multi-neuron)"
    description: ClassVar[str] = (
        "Map afferent synapses from EM onto multiple spiny morphologies, "
        "producing a circuit with physical internal connections and virtual external inputs."
    )
    coordinate_output_root: Path = Field(title="Output directory")

    class Initialize(Block):
        # We use a tuple instead of a list to avoid getting it taken as scan dimensions in the
        # scan config.
        neurons: tuple[NeuronEntry, ...] = Field(
            title="Neurons",
            description="Neurons to include in the multi-neuron circuit.",
            min_length=2,
        )
        physical_edge_population_name: str = Field(
            title="Physical edge population name",
            description="Edge population for connections between neurons in the set.",
            default="physical_connections",
        )
        virtual_edge_population_name: str = Field(
            title="Virtual edge population name",
            description="Edge population for connections from virtual neurons.",
            default="virtual_afferents",
        )
        biophysical_node_population: str = Field(
            title="Biophysical node population name",
            description="Node population for the physical neurons in the circuit.",
            default="biophysical_neurons",
        )
        virtual_node_population: str = Field(
            title="Virtual node population name",
            description="Node population for external presynaptic neurons.",
            default="virtual_afferent_neurons",
        )

    initialize: Initialize

    def enforce_no_multi_param(self) -> None:
        """Override: allow list-valued neurons field."""
