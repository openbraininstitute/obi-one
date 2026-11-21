"""ME-model synapse placement task configuration."""

from typing import ClassVar

from entitysdk import Client, models
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.library.entity_property_types import MappedPropertiesGroup
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.tasks.build_synaptome.blocks import (
    BlockGroup,
    SynapticModelPlacerUnion,
)
from obi_one.scientific.unions_and_references.distributions import (
    AllDistributionsReference,
    AllDistributionsUnion,
)
from obi_one.scientific.unions_and_references.morphology_locations import (
    MorphologyLocationsReference,
    SingleMorphologySamplingLocationUnion,
)
from obi_one.scientific.unions_and_references.synaptic_models import (
    SynapticModelReference,
    SynapticModelUnion,
)
from obi_one.scientific.unions_and_references.synaptome_input import (
    SynaptomeInput,
)


class MEModelSynapticModelPlacementScanConfig(InfoScanConfig):
    """Form for placing synaptic models on a single ME-model or a synaptome."""

    name: ClassVar[str] = "Synapse Placement"
    description: ClassVar[str] = (
        "Place synaptic models on a single ME-model, or add them to a synaptome that already "
        "has synapses."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.INFO,
            BlockGroup.POSTSYNAPTIC_NEURON,
            BlockGroup.SYNAPTIC_PHYSIOLOGY,
            BlockGroup.SYNAPSE_GROUPS,
        ],
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: {
            SynapticModelReference.__name__: "Select a synaptic model",
            AllDistributionsReference.__name__: (
                "Default: Built-in distribution (see field description)"
            ),
            MorphologyLocationsReference.__name__: "Select a placement strategy",
        },
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}",
            MappedPropertiesGroup.MORPHOLOGY: "/mapped-morphology-properties/{circuit_id}",
        },
    }

    class Initialize(Block):
        """Configuration for the single cell that receives incoming synapses."""

        title: ClassVar[str] = "Postsynaptic Neuron Initialization"

        me_model: SynaptomeInput = Field(
            title="Postsynaptic ME-model or synaptome",
            description=(
                "Existing single-cell ME-model, or synaptome that already has "
                "synapses, providing the morphology and electrophysiological properties of the "
                "postsynaptic neuron. New synapse groups are added to it. With a synaptome, "
                "its existing synapses are kept unchanged."
            ),
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
                SchemaKey.PARAMETER_ORDER_PRIORITY: 100,
            },
        )

    def input_entities(self, db_client: Client) -> list[models.Entity]:
        """Return the ME-model or synaptome the synaptome is built on."""
        return [self.initialize.me_model.entity(db_client=db_client)]

    info: Info = Field(
        title="Info",
        description="Information about the synapse placement.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.INFO,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    initialize: Initialize = Field(
        title="Postsynaptic ME-model or synaptome",
        description=(
            "Existing single-cell ME-model, or synaptome that already has synapses, "
            "providing the morphology and electrophysiological properties of the postsynaptic "
            "neuron receiving the incoming synapses."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.POSTSYNAPTIC_NEURON,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    synaptic_models: dict[str, SynapticModelUnion] = Field(
        default_factory=dict,
        title="Synaptic models",
        description="Synaptic physiology models available for incoming synapse groups.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [SynapticModelReference.__name__],
            SchemaKey.SINGULAR_NAME: "Synaptic Model",
            SchemaKey.GROUP: BlockGroup.SYNAPTIC_PHYSIOLOGY,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    distributions: dict[str, AllDistributionsUnion] = Field(
        default_factory=dict,
        title="Distributions",
        description="Distributions used by synaptic physiology models.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Distribution",
            SchemaKey.GROUP: BlockGroup.SYNAPTIC_PHYSIOLOGY,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    # Narrowed to the blocks that sample a morphology: placement calls `points_on`, which
    # per-neuron explicit locations do not implement -- their rows already name their neurons.
    morphology_locations: dict[str, SingleMorphologySamplingLocationUnion] = Field(
        default_factory=dict,
        title="Placement strategies",
        description="Reusable morphology-location strategies for incoming synapse groups.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [MorphologyLocationsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Placement Strategy",
            SchemaKey.GROUP: BlockGroup.SYNAPSE_GROUPS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    synapse_groups: dict[str, SynapticModelPlacerUnion] = Field(
        default_factory=dict,
        title="Synapse groups",
        description="Incoming synapse groups to add to the postsynaptic neuron.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [],
            SchemaKey.SINGULAR_NAME: "Synapse Group",
            SchemaKey.GROUP: BlockGroup.SYNAPSE_GROUPS,
            SchemaKey.GROUP_ORDER: 1,
        },
    )


class MEModelSynapticModelPlacementSingleConfig(
    MEModelSynapticModelPlacementScanConfig, SingleConfigMixin
):
    """Single-coordinate ME-model synapse placement config."""
