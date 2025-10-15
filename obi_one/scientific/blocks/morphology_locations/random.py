import morphio
import pandas  # noqa: ICN001
from pydantic import Field

from obi_one.scientific.blocks.morphology_locations.base import MorphologyLocationsBlock
from obi_one.scientific.library.morphology_locations import (
    _CEN_IDX,
    generate_neurite_locations_on,
)

_MIN_PD_SD = 0.1


class RandomMorphologyLocations(MorphologyLocationsBlock):
    """Completely random locations without constraint."""

    def _make_points(self, morphology: morphio.Morphology) -> pandas.DataFrame:
        locs = generate_neurite_locations_on(
            morphology,
            n_centers=1,
            n_per_center=self.number_of_locations,
            srcs_per_center=1,
            center_path_distances_mean=0.0,
            center_path_distances_sd=0.0,
            max_dist_from_center=None,
            lst_section_types=self.section_types,
            seed=self.random_seed,
        ).drop(columns=[_CEN_IDX])
        return locs

    def _check_parameter_values(self) -> None:
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.number_of_locations, list):  # noqa: SIM102
            if self.number_of_locations <= 0:
                msg = f"Number of locations: {self.number_of_locations} <= 0"
                raise ValueError(msg)


class RandomGroupedMorphologyLocations(MorphologyLocationsBlock):
    """Completely random locations, but grouped into abstract groups."""

    n_groups: int | list[int] = Field(
        default=1,
        name="Number of groups",
        description="Number of groups of locations to \
            generate",
    )

    def _make_points(self, morphology: morphio.Morphology) -> pandas.DataFrame:
        locs = generate_neurite_locations_on(
            morphology,
            n_centers=1,
            n_per_center=self.number_of_locations,
            srcs_per_center=self.n_groups,
            center_path_distances_mean=0.0,
            center_path_distances_sd=0.0,
            max_dist_from_center=None,
            lst_section_types=self.section_types,
            seed=self.random_seed,
        ).drop(columns=[_CEN_IDX])
        return locs

    def _check_parameter_values(self) -> None:
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.n_groups, list):  # noqa: SIM102
            if self.n_groups <= 0:
                msg = f"Number of groups: {self.n_groups} <= 0"
                raise ValueError(msg)
