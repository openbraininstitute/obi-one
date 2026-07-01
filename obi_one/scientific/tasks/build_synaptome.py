from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal

from pydantic import Discriminator, Field

from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.blocks.morphology_locations.random import RandomMorphologyLocations
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.unions.unions_distributions import (
    AllDistributionsReference,
    AllDistributionsUnion,
)
from obi_one.scientific.unions.unions_morphology_locations import MorphologyLocationUnion
from obi_one.scientific.unions.unions_synaptic_models import (
    SynapticModelReference,
    SynapticModelUnion,
)


class BlockGroup(StrEnum):
    """Block groups for the Build Synaptome form."""

    INFO = "Info"
    ME_MODEL = "ME-model"
    SYNAPTIC_PHYSIOLOGY = "Synaptic physiology"
    SYNAPSE_GROUPS = "Synapse groups"


class SingleCellModelContext(Block):
    """Single-cell model context for a synaptome build."""

    cell_model: MEModelFromID = Field(
        title="ME-model",
        description="Existing ME-model used as the post-synaptic cell context.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
        },
    )


class AfferentSynapseGroupBase(Block):
    """Common fields for an afferent synapse group."""

    group_name: str = Field(
        default="Afferent synapse group",
        title="Group name",
        description="Short user-facing name for this incoming synapse group.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_INPUT,
        },
    )
    placement_strategy: MorphologyLocationUnion = Field(
        default_factory=RandomMorphologyLocations,
        title="Placement strategy",
        description=(
            "Existing morphology-location block used to place this group's incoming synapses. "
            "The number of locations corresponds to the number of synapses."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_UNION,
        },
    )
    synaptic_model: SynapticModelReference | None = Field(
        default=None,
        title="Synaptic model",
        description="Synaptic physiology model assigned to this incoming synapse group.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: SynapticModelReference.__name__,
        },
    )


class ExcitatoryAfferentSynapseGroup(AfferentSynapseGroupBase):
    """Excitatory afferent synapse group."""

    title: ClassVar[str] = "Excitatory Afferent Synapse Group"

    synapse_type: Literal["excitatory"] = Field(
        default="excitatory",
        title="Synapse type",
        description="Excitatory afferent synapse group.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_CONSTANT,
        },
    )


class InhibitoryAfferentSynapseGroup(AfferentSynapseGroupBase):
    """Inhibitory afferent synapse group."""

    title: ClassVar[str] = "Inhibitory Afferent Synapse Group"

    synapse_type: Literal["inhibitory"] = Field(
        default="inhibitory",
        title="Synapse type",
        description="Inhibitory afferent synapse group.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_CONSTANT,
        },
    )


AfferentSynapseGroupUnion = Annotated[
    ExcitatoryAfferentSynapseGroup | InhibitoryAfferentSynapseGroup,
    Discriminator("type"),
]


class AfferentSynapseGroupReference(BlockReference):
    """A reference to an afferent synapse group block."""

    allowed_block_types: ClassVar[Any] = AfferentSynapseGroupUnion


class BuildSynaptomeScanConfig(ScanConfig):
    """Form for configuring a single-cell synaptome build."""

    single_coord_class_name: ClassVar[str] = "BuildSynaptomeSingleConfig"
    name: ClassVar[str] = "Build Synaptome"
    description: ClassVar[str] = "Configure a single-cell synaptome build."

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.INFO,
            BlockGroup.ME_MODEL,
            BlockGroup.SYNAPTIC_PHYSIOLOGY,
            BlockGroup.SYNAPSE_GROUPS,
        ],
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: {
            AfferentSynapseGroupReference.__name__: "Default: Synapse Group",
            SynapticModelReference.__name__: "Default: Synaptic Model",
            AllDistributionsReference.__name__: "Default: Distribution",
        },
    }

    info: Info = Field(
        title="Info",
        description="Information about the synaptome build.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.INFO,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    cell_context: SingleCellModelContext = Field(
        title="ME-model",
        description="Single-cell model context for the synaptome build.",
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
            SchemaKey.REFERENCE_TYPE: SynapticModelReference.__name__,
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
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
            SchemaKey.SINGULAR_NAME: "Distribution",
            SchemaKey.GROUP: BlockGroup.SYNAPTIC_PHYSIOLOGY,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    afferent_synapse_groups: dict[str, AfferentSynapseGroupUnion] = Field(
        default_factory=dict,
        title="Synapse groups",
        description="Incoming synapse groups to attach to the ME-model.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPE: AfferentSynapseGroupReference.__name__,
            SchemaKey.SINGULAR_NAME: "Synapse Group",
            SchemaKey.GROUP: BlockGroup.SYNAPSE_GROUPS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class BuildSynaptomeSingleConfig(BuildSynaptomeScanConfig, SingleConfigMixin):
    """Single-coordinate Build Synaptome config."""
