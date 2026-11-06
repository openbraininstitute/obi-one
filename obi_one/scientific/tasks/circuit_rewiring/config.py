import logging
from enum import StrEnum
from typing import Annotated, ClassVar

from entitysdk import Client, models
from pydantic import Discriminator, Field, NonNegativeInt

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.entity_property_types import MappedPropertiesGroup
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.unions_and_references.circuit import CircuitDiscriminator
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    ALL_NEURON_SETS_REFERENCE_TYPES,
    ALL_NEURON_SETS_REFERENCE_UNION,
    NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
    NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION,
    NEURONSimulationNeuronSetUnion,
)
from obi_one.scientific.unions_and_references.distributions import (
    AllDistributionsReference,
    AllDistributionsUnion,
)
from obi_one.scientific.unions_and_references.structural_conn_models import (
    STRUCTURAL_CONN_MODELS_REFERENCE_TYPES,
    PathwayStructuralConnModelReference,
    StructuralConnModelUnion,
)

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    NEURON_SETS_BLOCK_GROUP = "Neuron sets"
    CONN_MODELS_BLOCK_GROUP = "Connectivity models"
    DISTRIBUTIONS_BLOCK_GROUP = "Distributions"
    PATHWAYS_BLOCK_GROUP = "Pathways"


class CircuitConnectivityPathway(Block):
    """Connectivity specification for a single source -> target pathway.

    Upon execution, the referenced ``conn_model`` (a ``PathwayStructuralConnModel``) decides
    which ordered pairs of a source neuron (from ``source_neuron_set``) and a target neuron
    (from ``target_neuron_set``) become connected. For every drawn connection, an integer count
    is sampled from ``synapses_per_connection`` and that many identical edges (same source and
    target neuron) are placed in the new edge population. Only the connectivity is generated; no
    further edge properties are added.
    """

    title: ClassVar[str] = "Pathway connectivity"

    source_neuron_set: ALL_NEURON_SETS_REFERENCE_UNION = Field(
        title="Source neuron set",
        description="Set of neurons that form the presynaptic (source) side of the connections."
        " May be a virtual neuron set (e.g. for feedforward/external input projections).",
        json_schema_extra={  # ty:ignore[invalid-argument-type]
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: ALL_NEURON_SETS_REFERENCE_TYPES,
        },
    )
    target_neuron_set: NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION = Field(
        title="Target neuron set",
        description="Set of neurons that form the postsynaptic (target) side of the connections."
        " Must be non-virtual: nothing simulates incoming synapses onto a virtual neuron.",
        json_schema_extra={  # ty:ignore[invalid-argument-type]
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
        },
    )
    conn_model: PathwayStructuralConnModelReference = Field(
        title="Connectivity model",
        description="Structural connectivity model that decides which source/target neuron pairs"
        " become connected for this pathway (e.g. Erdos-Renyi or distance-dependent).",
        json_schema_extra={  # ty:ignore[invalid-argument-type]
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: STRUCTURAL_CONN_MODELS_REFERENCE_TYPES,
        },
    )
    synapses_per_connection: AllDistributionsReference = Field(
        title="Synapses per connection",
        description="Distribution from which an integer number of synapses (edges) is drawn for"
        " each connection. That many identical edges between the same source and target neuron"
        " are placed in the edge population. Non-positive samples are clamped to 1.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
        },
    )


CircuitConnectivityPathwayUnion = Annotated[
    CircuitConnectivityPathway,
    Discriminator("type"),
]


class CircuitRewiringScanConfig(InfoScanConfig):
    """ScanConfig for adding a new connectivity edge population to a SONATA circuit."""

    name: ClassVar[str] = "Circuit Rewiring"
    description: ClassVar[str] = (
        "Adds a new edge population to a SONATA circuit, connecting neurons according to"
        " user-specified source/target neuron sets and a structural connectivity model per"
        " pathway. The new edge population describes only which neurons are connected; no"
        " additional edge parameters are added. The edge population is also registered in the"
        " circuit configuration (circuit_config.json)."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP,
            BlockGroup.NEURON_SETS_BLOCK_GROUP,
            BlockGroup.CONN_MODELS_BLOCK_GROUP,
            BlockGroup.DISTRIBUTIONS_BLOCK_GROUP,
            BlockGroup.PATHWAYS_BLOCK_GROUP,
        ],
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}",
        },
    }

    class Initialize(Block):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit",
            description="Circuit to add a new connectivity edge population to.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
            },
        )
        edge_population_name: str = Field(
            default="rewired",
            min_length=1,
            title="Edge population name",
            description="Name of the new edge population to add to the circuit. Must not already"
            " exist in the circuit.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
            },
        )
        seed: NonNegativeInt = Field(
            default=0,
            title="Random seed",
            description="Seed for the random generator used to draw the connections.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
            },
        )

    def input_entities(self, db_client: Client) -> list[models.Entity]:
        input_entities = []
        if isinstance(self.initialize.circuit, CircuitFromID):
            input_entities.extend([self.initialize.circuit.entity(db_client=db_client)])
        elif isinstance(self.initialize.circuit, list):
            for circuit in self.initialize.circuit:
                if isinstance(circuit, CircuitFromID):
                    input_entities.extend([circuit.entity(db_client=db_client)])
        return input_entities

    info: Info = Field(
        title="Info",
        description="Information about the rewiring campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the circuit rewiring campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    neuron_sets: dict[str, NEURONSimulationNeuronSetUnion] = Field(  # ty:ignore[no-matching-overload]
        title="Neuron sets",
        default_factory=dict,
        description="Neuron sets referenced by the pathways as sources and targets. Virtual"
        " neuron sets may be used as sources only (e.g. for feedforward/external input"
        " projections); targets must be non-virtual.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: ALL_NEURON_SETS_REFERENCE_TYPES,
            SchemaKey.SINGULAR_NAME: "Neuron Set",
            SchemaKey.GROUP: BlockGroup.NEURON_SETS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    structural_conn_models: dict[str, StructuralConnModelUnion] = Field(  # ty:ignore[no-matching-overload]
        title="Connectivity models",
        default_factory=dict,
        description="Structural connectivity models referenced by the pathways (e.g. Erdos-Renyi"
        " or distance-dependent).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: STRUCTURAL_CONN_MODELS_REFERENCE_TYPES,
            SchemaKey.SINGULAR_NAME: "Connectivity Model",
            SchemaKey.GROUP: BlockGroup.CONN_MODELS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    distributions: dict[str, AllDistributionsUnion] = Field(
        title="Distributions",
        default_factory=dict,
        description="Distributions referenced by the pathways (e.g. for the number of synapses"
        " per connection).",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Distribution",
            SchemaKey.GROUP: BlockGroup.DISTRIBUTIONS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    pathways: dict[str, CircuitConnectivityPathwayUnion] = Field(
        title="Pathways",
        default_factory=dict,
        description="Source/target pathways, each with the connectivity model used to wire it."
        " The new edge population is the union of the connections drawn for every pathway.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [],
            SchemaKey.SINGULAR_NAME: "Pathway",
            SchemaKey.GROUP: BlockGroup.PATHWAYS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class CircuitRewiringSingleConfig(CircuitRewiringScanConfig, SingleConfigMixin):
    """Adds a new connectivity edge population to a SONATA circuit.

    Connections are drawn per pathway (source neuron set, target neuron set) using the pathway's
    structural connectivity model. The new edge population lists only which neurons are connected
    and is registered in the circuit configuration.
    """
