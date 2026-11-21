"""Blocks for ME-model synapse placement."""

from enum import StrEnum
from typing import Annotated, ClassVar

from pydantic import Discriminator, Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.unions_and_references.morphology_locations import (
    MorphologyLocationsReference,
)
from obi_one.scientific.unions_and_references.synaptic_models import (
    SynapticModelReference,
)


class BlockGroup(StrEnum):
    """Block groups for the Synapse Placement form."""

    INFO = "Info"
    POSTSYNAPTIC_NEURON = "Postsynaptic neuron"
    SYNAPTIC_PHYSIOLOGY = "Synaptic physiology"
    SYNAPSE_GROUPS = "Synapse groups"


class SynapticModelPlacer(Block):
    """Places synapses with a given synaptic model on a single-cell morphology."""

    title: ClassVar[str] = "Synaptic model placer"

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
            "The number of locations corresponds to the number of synapses. Each location group "
            "becomes a distinct presynaptic neuron, so a strategy with a group count (e.g. "
            "Random Grouped Morphology Locations) sets how many presynaptic neurons the synapses "
            "come from; strategies without one place every synapse from a single presynaptic "
            "neuron."
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
