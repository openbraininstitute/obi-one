from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt

from obi_one.core.block import Block
from obi_one.core.exception import ConfigValidationError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.morphology_locations.base import (
    NormalizedSectionOffset,
    SectionID,
)
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
)


class NeuronMorphologyLocationPoint(BaseModel):
    """One location, on one named neuron: exactly a SONATA compartment-set row."""

    model_config = ConfigDict(extra="forbid")

    node_id: NonNegativeInt = Field(
        title="Node ID",
        description="Identifier of the neuron this location belongs to.",
    )
    section_id: SectionID
    offset: NormalizedSectionOffset


class PerNeuronExplicitMorphologyLocations(Block):
    """Exact points chosen on exact neurons.

    Each point names its own neuron, so selecting several points across several neurons stays a
    single block. Unlike `ExplicitMorphologyLocations`, the points are not repeated across a
    neuron set, so nothing is targeted that was not picked.
    """

    title: ClassVar[str] = "Per Neuron Explicit Morphology Locations"

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_MORPHOLOGY_LOCATIONS,
            SchemaKey.FALSE_MESSAGE: (
                "Morphology-location targeting is not supported for this circuit."
            ),
        },
    }

    locations: Annotated[tuple[NeuronMorphologyLocationPoint, ...], Field(min_length=1)] | None = (
        Field(
            default=None,
            title="Explicit locations",
            description=(
                "The exact points to target, each on a named neuron. Click anywhere on a neuron in "
                "the 3D view to add one, or type it in by hand. Each row is a single point: which "
                "neuron it belongs to, which branch of that neuron it sits on, and how far along "
                "that branch it is — 0 is the start of the branch, 1 is the end, 0.5 is halfway. "
                "Branch 0 is always the soma. At least one point is required."
            ),
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MORPHOLOGY_LOCATION_SELECTION,
            },
        )
    )

    def compartment_rows(self) -> tuple[tuple[int, int, float], ...]:
        """Return the selected points as SONATA `[node_id, section_id, offset]` rows."""
        if not self.locations:
            msg = (
                "Per-neuron explicit morphology locations must contain at least one point "
                "before they can be used as a stimulus or recording target."
            )
            raise ConfigValidationError(msg)

        return tuple(
            (location.node_id, location.section_id, location.offset) for location in self.locations
        )
