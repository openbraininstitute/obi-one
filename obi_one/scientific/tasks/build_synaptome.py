from enum import StrEnum
from typing import Annotated, ClassVar

from pydantic import Discriminator, Field

from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.entity_property_types import MappedPropertiesGroup
from obi_one.scientific.unions_and_references.distributions import (
    AllDistributionsReference,
    AllDistributionsUnion,
)
from obi_one.scientific.unions_and_references.morphology_locations import (
    MorphologyLocationsReference,
    MorphologyLocationUnion,
)
from obi_one.scientific.unions_and_references.synaptic_models import (
    SynapticModelReference,
    SynapticModelUnion,
)


class BlockGroup(StrEnum):
    """Block groups for the ME-model Synapse Placement form."""

    INFO = "Info"
    ME_MODEL = "ME-model"
    SYNAPTIC_PHYSIOLOGY = "Synaptic physiology"
    SYNAPSE_GROUPS = "Synapse groups"


class SynapticModelPlacer(Block):
    """Places synapses with a given synaptic model on a single-cell morphology."""

    synaptic_model: SynapticModelReference = Field(
        title="Synaptic model",
        description="Synaptic physiology model assigned to this incoming synapse group.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [SynapticModelReference.__name__],
        },
    )
    placement_strategy: MorphologyLocationsReference = Field(
        title="Placement strategy",
        description=(
            "Existing morphology-location block used to place this group's incoming synapses. "
            "The number of locations corresponds to the number of synapses."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPES: [MorphologyLocationsReference.__name__],
        },
    )


SynapticModelPlacerUnion = Annotated[
    SynapticModelPlacer,
    Discriminator("type"),
]


class SynapticModelPlacerReference(BlockReference):
    allowed_block_types = SynapticModelPlacerUnion


class MEModelSynapticModelPlacementScanConfig(ScanConfig):
    """Form for placing synaptic models on a single ME-model."""

    single_coord_class_name: ClassVar[str] = "MEModelSynapticModelPlacementSingleConfig"
    name: ClassVar[str] = "ME-model Synapse Placement"
    description: ClassVar[str] = "Place synaptic models on a single ME-model."

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.INFO,
            BlockGroup.ME_MODEL,
            BlockGroup.SYNAPTIC_PHYSIOLOGY,
            BlockGroup.SYNAPSE_GROUPS,
        ],
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: {
            SynapticModelReference.__name__: "Default: Synaptic Model",
            AllDistributionsReference.__name__: "Default: Distribution",
            MorphologyLocationsReference.__name__: "Default: Placement Strategy",
        },
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}",
            MappedPropertiesGroup.MORPHOLOGY: "/mapped-morphology-properties/{circuit_id}",
        },
    }

    class Initialize(Block):
        """ME-model to use as the postsynaptic cell."""

        me_model: MEModelFromID = Field(
            title="ME-model",
            description="Existing ME-model supplied as the postsynaptic cell context.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
                SchemaKey.PARAMETER_ORDER_PRIORITY: 100,
            },
        )

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
        title="ME-model",
        description="ME-model to use as the postsynaptic cell.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.ME_MODEL,
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
    morphology_locations: dict[str, MorphologyLocationUnion] = Field(
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
        description="Incoming synapse groups to attach to the ME-model.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [SynapticModelPlacerReference.__name__],
            SchemaKey.SINGULAR_NAME: "Synaptic Model Placer",
            SchemaKey.GROUP: BlockGroup.SYNAPSE_GROUPS,
            SchemaKey.GROUP_ORDER: 1,
        },
    )


class MEModelSynapticModelPlacementSingleConfig(
    MEModelSynapticModelPlacementScanConfig, SingleConfigMixin
):
    """Single-coordinate ME-model synapse placement config."""
