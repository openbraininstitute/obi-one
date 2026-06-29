import logging
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.from_id.circuit_from_id import (
    MEModelWithSynapsesCircuitFromID,
)
from obi_one.scientific.library.entity_property_types import MappedPropertiesGroup
from obi_one.scientific.library.memodel_circuit import MEModelWithSynapsesCircuit
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BlockGroup,
    SimulationSingleConfigMixin,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationScanConfig,
)
from obi_one.scientific.unions.unions_morphology_locations import (
    MorphologyLocationsReference,
    MorphologyLocationUnion,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    MEModelWithSynapsesNeuronSetUnion,
    NeuronSetReference,
)

L = logging.getLogger(__name__)


MEModelWithSynapsesCircuitDiscriminator = Annotated[
    MEModelWithSynapsesCircuit | MEModelWithSynapsesCircuitFromID, Field(discriminator="type")
]


class MEModelWithSynapsesCircuitSimulationScanConfig(CircuitSimulationScanConfig):
    """MEModelWithSynapsesCircuitSimulationScanConfig."""

    single_coord_class_name: ClassVar[str] = "MEModelWithSynapsesCircuitSimulationSingleConfig"
    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"
    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            BlockGroup.DISTRIBUTIONS_BLOCK_GROUP,
            BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            BlockGroup.TARGETING_BLOCK_GROUP,
            BlockGroup.CIRCUIT_MANIPULATIONS_GROUP,
            BlockGroup.EVENTS_GROUP,
        ],
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}",
            # TODO: Use {source_id} once the UI supports source-neutral endpoint placeholders.
            MappedPropertiesGroup.MORPHOLOGY_SOURCE: (
                "/mapped-morphology-source-properties/{circuit_id}"
            ),
        },
    }

    class Initialize(CircuitSimulationScanConfig.Initialize):
        circuit: (
            MEModelWithSynapsesCircuitDiscriminator | list[MEModelWithSynapsesCircuitDiscriminator]
        ) = Field(
            title="MEModel With Synapses",
            description="MEModel with synapses to simulate.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
                SchemaKey.PARAMETER_ORDER_PRIORITY: 100,
            },
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    morphology_locations: dict[str, MorphologyLocationUnion] = Field(
        default_factory=dict,
        title="Morphology Locations",
        description="Parameterized locations on the neurites of the morphology.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: MorphologyLocationsReference.__name__,
            SchemaKey.SINGULAR_NAME: "Morphology Location",
            SchemaKey.GROUP: BlockGroup.TARGETING_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    neuron_sets: dict[str, MEModelWithSynapsesNeuronSetUnion] = Field(
        default_factory=dict,
        description="Neuron sets for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
            SchemaKey.SINGULAR_NAME: "Neuron Set",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class MEModelWithSynapsesCircuitSimulationSingleConfig(
    MEModelWithSynapsesCircuitSimulationScanConfig, SimulationSingleConfigMixin
):
    """Only allows single values."""
