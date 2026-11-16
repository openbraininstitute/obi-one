import logging
from typing import Annotated, ClassVar

from pydantic import Field

from obi_one.core.fill_none_references import BlockDefault
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.neuron_sets.specific import AllVirtualNeurons
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
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    ALL_NEURON_SETS_REFERENCE_TYPES,
    NEURONMEModelWithSynapsesNeuronSetUnion,
)
from obi_one.scientific.unions_and_references.morphology_locations import (
    MorphologyLocationsReference,
    SingleMorphologySamplingLocationUnion,
)
from obi_one.scientific.unions_and_references.neuron_sets import VirtualNeuronSetReference
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag

L = logging.getLogger(__name__)


MEModelWithSynapsesCircuitDiscriminator = Annotated[
    MEModelWithSynapsesCircuit | MEModelWithSynapsesCircuitFromID, Field(discriminator="type")
]


class MEModelWithSynapsesCircuitSimulationScanConfig(CircuitSimulationScanConfig):
    """MEModelWithSynapsesCircuitSimulationScanConfig."""

    name: ClassVar[str] = "Simulation Campaign"
    description: ClassVar[str] = "SONATA simulation campaign"
    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.TARGETING_BLOCK_GROUP,
            BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            BlockGroup.DISTRIBUTIONS_BLOCK_GROUP,
            BlockGroup.CIRCUIT_MANIPULATIONS_GROUP,
            BlockGroup.EVENTS_GROUP,
        ],
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}",
            MappedPropertiesGroup.MORPHOLOGY: ("/mapped-morphology-properties/{circuit_id}"),
            MappedPropertiesGroup.NEURONAL_MANIPULATION: (
                "/circuit-neuronal-manipulation-properties-by-neuron-set"
            ),
        },
    }

    @staticmethod
    def default_blocks() -> dict[str, BlockDefault]:
        """An unset spike source replays from the synaptome's inputs, not its one neuron."""
        return {
            ReferenceTag.SPIKE_STIMULUS_SOURCE: BlockDefault(
                VirtualNeuronSetReference,
                "neuron_sets",
                CircuitSimulationScanConfig.default_virtual_node_set_name,
                AllVirtualNeurons,
            ),
        }

    class Initialize(CircuitSimulationScanConfig.Initialize):
        circuit: (
            MEModelWithSynapsesCircuitDiscriminator | list[MEModelWithSynapsesCircuitDiscriminator]
        ) = Field(
            title="ME-model with synapses",
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

    neuron_sets: dict[str, NEURONMEModelWithSynapsesNeuronSetUnion] = Field(  # ty:ignore[no-matching-overload]
        title="Neuron sets",
        default_factory=dict,
        description="Neuron sets for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: ALL_NEURON_SETS_REFERENCE_TYPES,
            SchemaKey.SINGULAR_NAME: "Neuron Set",
            SchemaKey.GROUP: BlockGroup.TARGETING_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    # Widened back after the circuit narrowing: this configuration simulates a single neuron, so
    # hand-picked section/offset points are unambiguous here. Per-neuron explicit locations stay
    # out for the same reason -- there is only one neuron for a point to belong to.
    morphology_locations: dict[str, SingleMorphologySamplingLocationUnion] = Field(
        default_factory=dict,
        title="Morphology locations",
        description=(
            "Reusable rules for selecting precise locations on neuronal morphologies. "
            "Stimuli can reference these locations to target compartments instead of whole cells."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [MorphologyLocationsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Morphology Location",
            SchemaKey.GROUP: BlockGroup.TARGETING_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )


class MEModelWithSynapsesCircuitSimulationSingleConfig(
    MEModelWithSynapsesCircuitSimulationScanConfig, SimulationSingleConfigMixin
):
    """Only allows single values."""
