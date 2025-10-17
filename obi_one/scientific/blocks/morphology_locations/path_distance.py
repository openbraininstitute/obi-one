import morphio
import pandas  # noqa: ICN001
from pydantic import Field

from obi_one.scientific.blocks.morphology_locations.base import MorphologyLocationsBlock
from obi_one.scientific.library.morphology_locations import (
    _CEN_IDX,
    generate_neurite_locations_on,
)


class PathDistanceMorphologyLocations(MorphologyLocationsBlock):
    """Locations around a specified path distance."""

    path_dist_mean: float | list[float] = Field(
        name="Path distance mean",
        description="Mean of a Gaussian, defined on soma path distance in um. Used to determine \
            locations.",
    )
    path_dist_tolerance: float | list[float] = Field(
        name="Path distance tolerance",
        description="Amount of deviation in um from mean path distance that is tolerated. Must be \
            > 1.0",
    )

    def _make_points(self, morphology: morphio.Morphology) -> pandas.DataFrame:
        locs = generate_neurite_locations_on(
            morphology,
            n_centers=self.number_of_locations,
            n_per_center=1,
            srcs_per_center=1,
            center_path_distances_mean=self.path_dist_mean,
            center_path_distances_sd=0.1 * self.path_dist_tolerance,
            max_dist_from_center=0.9 * self.path_dist_tolerance,
            lst_section_types=self.section_types,
            seed=self.random_seed,
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
