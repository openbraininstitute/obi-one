from typing import Annotated, ClassVar

import morphio
import pandas as pd
from pydantic import Field, NonNegativeFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.morphology_locations.base import (
    GeneratedMorphologyLocationsBlock,
)
from obi_one.scientific.library.morphology_locations import (
    generate_locations_in_path_distance_band,
)

PathDistanceToleranceParameter = Annotated[float, Field(ge=1.0)]


class PathDistanceMorphologyLocations(GeneratedMorphologyLocationsBlock):
    """Locations uniformly sampled near a specified soma path distance."""

    title: ClassVar[str] = "Path distance morphology locations"

    path_dist_mean: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=100.0,
        title="Path distance sampling mean",
        description=(
            "Center of the soma path-distance band that locations are sampled from. "
            "Final locations are sampled uniformly from valid morphology intervals within "
            "the path-distance tolerance."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    path_dist_tolerance: PathDistanceToleranceParameter | list[PathDistanceToleranceParameter] = (
        Field(
            default=50.0,
            title="Max distance to path distance sampling mean",
            description=(
                "Allowed deviation from the target soma path distance. Locations are sampled "
                "uniformly from valid morphology intervals within this tolerance. Must be at "
                "least 1.0."
            ),
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.MICROMETERS,
            },
        )
    )

    def _make_points(self, morphology: morphio.Morphology) -> pd.DataFrame:
        return generate_locations_in_path_distance_band(
            morphology,
            n_locations=self.number_of_locations,  # ty:ignore[invalid-argument-type]
            min_path_distance=self.path_dist_mean - self.path_dist_tolerance,  # ty:ignore[unsupported-operator]
            max_path_distance=self.path_dist_mean + self.path_dist_tolerance,  # ty:ignore[unsupported-operator]
            lst_section_types=self.section_types,  # ty:ignore[invalid-argument-type]
            seed=self.random_seed,  # ty:ignore[invalid-argument-type]
        )

    def _check_parameter_values(self) -> None:
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.path_dist_mean, list):  # ruff: ignore[collapsible-if]
            if self.path_dist_mean < 0:
                msg = f"Path distance mean: {self.path_dist_mean} < 0"
                raise ValueError(msg)

        if not isinstance(self.path_dist_tolerance, list):  # ruff: ignore[collapsible-if]
            if self.path_dist_tolerance < 1.0:
                msg = f"Path dist tolerance: {self.path_dist_tolerance} < 1.0 (numerical stability)"
                raise ValueError(msg)
