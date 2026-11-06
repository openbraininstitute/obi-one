import logging
from enum import StrEnum
from typing import Annotated, ClassVar, Self

from entitysdk import Client, models
from pydantic import Discriminator, Field, NonNegativeInt, model_validator

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
    NEURONSimulationNeuronSetUnion,
)
from obi_one.scientific.unions_and_references.distributions import (
    AllDistributionsReference,
    AllDistributionsUnion,
)
from obi_one.scientific.unions_and_references.morphology_locations import (
    NonGroupedMorphologyLocationsReference,
    NonGroupedMorphologyLocationUnion,
)
from obi_one.scientific.unions_and_references.structural_conn_models import (
    STRUCTURAL_CONN_MODELS_REFERENCE_TYPES,
    PathwayStructuralConnModelReference,
    StructuralConnModelUnion,
)
from obi_one.scientific.unions_and_references.synaptic_models import (
    SynapticModelReference,
    SynapticModelUnion,
)

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    NEURON_SETS_BLOCK_GROUP = "Neuron sets"
    CONN_MODELS_BLOCK_GROUP = "Connectivity models"
    DISTRIBUTIONS_BLOCK_GROUP = "Distributions"
    SYNAPTIC_MODELS_BLOCK_GROUP = "Synaptic models"
    MORPHOLOGY_LOCATIONS_BLOCK_GROUP = "Morphology locations"
    PATHWAYS_BLOCK_GROUP = "Pathways"


class CircuitConnectivityPathway(Block):
    """Connectivity specification for a single source -> target pathway.

    Upon execution, the referenced ``conn_model`` (a ``PathwayStructuralConnModel``) decides
    which ordered pairs of a source neuron (from ``source_neuron_set``) and a target neuron
    become connected. The target neurons are the neuron set specified in the referenced
    ``morphology_locations`` block. For every drawn connection, an integer count is sampled from
    ``synapses_per_connection`` and that many identical edges (same source and target neuron)
    are placed in the new edge population. Each edge is given a location on the postsynaptic
    neuron's morphology by ``morphology_locations`` and its physiological parameters by
    ``synaptic_model``; no other edge properties are added.
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
    synaptic_model: SynapticModelReference = Field(
        title="Synaptic model",
        description="Synaptic model that provides the physiological parameters of the synapses"
        " (edges) of this pathway, e.g. a Tsodyks-Markram model. Every synapse draws its own"
        " parameter values from the model's distributions, and the mechanism files the model"
        " needs are copied into the circuit.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [SynapticModelReference.__name__],
        },
    )
    morphology_locations: NonGroupedMorphologyLocationsReference = Field(
        title="Postsynaptic morphology locations",
        description="Morphology-locations block that parameterizes where the generated"
        " connections are located on the postsynaptic neuron. The neuron set specified in this"
        " block defines the target (postsynaptic) neurons of the pathway and is required. Each"
        " connection (edge) receives one location on the morphology of its target neuron, written"
        " as the afferent location edge properties. As in Build Synaptome, the number of"
        " locations per target neuron equals the number of edges it receives, so the block's own"
        " number of locations is overridden. Explicit and grouped location blocks are not"
        " available.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [NonGroupedMorphologyLocationsReference.__name__],
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
        " pathway. The new edge population describes which neurons are connected, where each"
        " connection is located on the postsynaptic neuron (afferent location properties) and the"
        " physiological parameters of each synapse (from a synaptic model); no other edge"
        " parameters are added. The edge population is also registered in the"
        " circuit configuration (circuit_config.json)."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP,
            BlockGroup.NEURON_SETS_BLOCK_GROUP,
            BlockGroup.CONN_MODELS_BLOCK_GROUP,
            BlockGroup.DISTRIBUTIONS_BLOCK_GROUP,
            BlockGroup.SYNAPTIC_MODELS_BLOCK_GROUP,
            BlockGroup.MORPHOLOGY_LOCATIONS_BLOCK_GROUP,
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
        description="Neuron sets referenced by the pathways: as sources directly, and as targets"
        " via the neuron set of the pathway's morphology locations. Virtual neuron sets may be"
        " used as sources only (e.g. for feedforward/external input projections); targets must"
        " be biophysical.",
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
    # NOTE: Unset distribution references of the synaptic models are not filled in here: sampling
    # falls back to each model's own default distribution (`resolve_distribution`), so results are
    # correct, but the defaults used are not recorded as explicit blocks in the saved config.
    # Recording them may be preferable in the future (as SynapseParameterizationScanConfig does
    # via `default_blocks()`), but this requires moving `_distribution_defaults()` out of the
    # synapse parameterization config into a shared location first.
    synaptic_models: dict[str, SynapticModelUnion] = Field(
        title="Synaptic models",
        default_factory=dict,
        description="Synaptic models referenced by the pathways. Their parameter distributions"
        " are taken from the distributions above; unset ones use the model's defaults.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [SynapticModelReference.__name__],
            SchemaKey.SINGULAR_NAME: "Synaptic Model",
            SchemaKey.GROUP: BlockGroup.SYNAPTIC_MODELS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    morphology_locations: dict[str, NonGroupedMorphologyLocationUnion] = Field(
        title="Morphology locations",
        default_factory=dict,
        description="Morphology-location blocks referenced by the pathways to parameterize where"
        " connections are placed on the postsynaptic neuron.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [NonGroupedMorphologyLocationsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Morphology Locations",
            SchemaKey.GROUP: BlockGroup.MORPHOLOGY_LOCATIONS_BLOCK_GROUP,
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

    @model_validator(mode="after")
    def require_target_neuron_set_in_morphology_locations(self) -> Self:
        """Require every pathway's morphology locations block to specify the target neuron set.

        TODO(re-think): The target neurons of a pathway are currently defined by the ``neuron_set``
        of its morphology locations block, and that field is required here. This couples target
        selection to a block whose purpose is geometry: the target is less visible on the
        pathway, and pathways with different targets cannot share a morphology locations block.
        We may want to re-think this in the future, e.g. by reintroducing a dedicated target
        neuron set on the pathway, or by allowing the field to be omitted with a default.
        """
        for pathway_name, pathway in self.pathways.items():
            reference = pathway.morphology_locations
            # Look the block up by name rather than via `reference.block`, which is only
            # available once all references have been resolved.
            block = self.morphology_locations.get(reference.block_name)
            if block is not None and getattr(block, "neuron_set", None) is None:
                msg = (
                    f"Pathway '{pathway_name}': the morphology locations block"
                    f" '{reference.block_name}' must specify a neuron set, as it defines the"
                    " target (postsynaptic) neurons of the pathway."
                )
                raise ValueError(msg)
        return self


class CircuitRewiringSingleConfig(CircuitRewiringScanConfig, SingleConfigMixin):
    """Adds a new connectivity edge population to a SONATA circuit.

    Connections are drawn per pathway (source neuron set, target neuron set) using the pathway's
    structural connectivity model. The new edge population lists which neurons are connected, the
    postsynaptic location of each connection and its synaptic parameters, and is registered in
    the circuit configuration.
    """
