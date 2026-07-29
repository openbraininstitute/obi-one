from typing import ClassVar

import morphio
import pandas  # noqa: ICN001
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.morphology_locations.base import MorphologyLocationsBlock
from obi_one.scientific.library.morphology_locations import (
    _CEN_IDX,
    generate_neurite_locations_on,
)


class PathDistanceMorphologyLocations(MorphologyLocationsBlock):
    """Locations uniformly sampled near a specified soma path distance."""

    title: ClassVar[str] = "Path Distance Morphology Locations"

    path_dist_mean: float | list[float] = Field(
        title="Path Distance Mean",
        description=(
            "Target soma path distance for generated locations. Candidate morphology intervals "
            "are centered around this distance."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    path_dist_tolerance: float | list[float] = Field(
        title="Path Distance Tolerance",
        description=(
            "Allowed deviation from the target soma path distance. Locations are sampled "
            "uniformly from valid morphology intervals within this tolerance. Must be greater "
            "than 1.0."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )

    def _make_points(self, morphology: morphio.Morphology) -> pandas.DataFrame:
        locs = generate_neurite_locations_on(
            morphology,
            n_centers=self.number_of_locations,  # ty:ignore[invalid-argument-type]
            n_per_center=1,
            srcs_per_center=1,
            center_path_distances_mean=self.path_dist_mean,  # ty:ignore[invalid-argument-type]
            center_path_distances_sd=0.1 * self.path_dist_tolerance,  # ty:ignore[unsupported-operator]
            max_dist_from_center=0.9 * self.path_dist_tolerance,  # ty:ignore[unsupported-operator]
            lst_section_types=self.section_types,  # ty:ignore[invalid-argument-type]
            seed=self.random_seed,  # ty:ignore[invalid-argument-type]
        ).drop(columns=[_CEN_IDX])
        return locs

    def _check_parameter_values(self) -> None:
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.path_dist_mean, list):  # noqa: SIM102
            if self.path_dist_mean < 0:
                msg = f"Path distance mean: {self.path_dist_mean} < 0"
                raise ValueError(msg)

        if not isinstance(self.path_dist_tolerance, list):  # noqa: SIM102
            if self.path_dist_tolerance < 1.0:
                msg = f"Path dist tolerance: {self.path_dist_tolerance} < 1.0 (numerical stability)"
                raise ValueError(msg)
