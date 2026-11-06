from typing import Annotated, Any, ClassVar, get_args

from pydantic import BeforeValidator, Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.morphology_locations.clustered import (
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.explicit import ExplicitMorphologyLocations
from obi_one.scientific.blocks.morphology_locations.path_distance import (
    PathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.random import (
    RandomMorphologyLocations,
)

# Blocks whose ``n_groups`` field was previously carried by a dedicated "Grouped" subclass.
# Those subclasses were folded into their base block (which now owns ``n_groups``), so configs
# saved with the retired discriminator are remapped onto the base before union discrimination.
# The saved ``n_groups`` value is preserved; every other field is left untouched.
_RETIRED_MORPHOLOGY_LOCATION_TYPES = {
    "RandomGroupedMorphologyLocations": RandomMorphologyLocations.__name__,
    "ClusteredGroupedMorphologyLocations": ClusteredMorphologyLocations.__name__,
}


def _remap_retired_type(data: Any) -> Any:
    """Rewrite a retired grouped-location ``type`` to its surviving base block."""
    if isinstance(data, dict):
        current = data.get("type")
        replacement = _RETIRED_MORPHOLOGY_LOCATION_TYPES.get(current)
        if replacement is not None:
            return {**data, "type": replacement}
    return data


# Locations sampled across the morphologies of a targeted neuron set. Every neuron receives its
# own sampled locations, so a section id always refers to the morphology it was sampled on.
_GENERATED_MORPHOLOGY_LOCATIONS = (
    ClusteredMorphologyLocations
    | ClusteredPathDistanceMorphologyLocations
    | PathDistanceMorphologyLocations
    | RandomMorphologyLocations
)

_ALL_MORPHOLOGY_LOCATIONS = _GENERATED_MORPHOLOGY_LOCATIONS | ExplicitMorphologyLocations

MorphologyLocationUnion = Annotated[
    _ALL_MORPHOLOGY_LOCATIONS,
    BeforeValidator(_remap_retired_type),
    Discriminator("type"),
]

# Explicit locations name a section and offset but no cell, so on a multi-neuron circuit the same
# branch id means a different branch on every morphology. They are therefore offered only for
# single-neuron configurations.
CircuitMorphologyLocationUnion = Annotated[
    _GENERATED_MORPHOLOGY_LOCATIONS,
    BeforeValidator(_remap_retired_type),
    Discriminator("type"),
]


class MorphologyLocationsReference(BlockReference):
    """Reference to a block that generates morphology locations."""

    allowed_block_types: ClassVar[Any] = MorphologyLocationUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(get_args(MorphologyLocationUnion)[0])
    }


__all__ = [
    "CircuitMorphologyLocationUnion",
    "MorphologyLocationUnion",
    "MorphologyLocationsReference",
]
