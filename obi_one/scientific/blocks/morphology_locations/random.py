from typing import ClassVar

import morphio
import pandas as pd

from obi_one.scientific.blocks.morphology_locations.base import (
    GeneratedMorphologyLocationsBlock,
)
from obi_one.scientific.library.morphology_locations import (
    _CEN_IDX,
    generate_neurite_locations_on,
)


class RandomMorphologyLocations(GeneratedMorphologyLocationsBlock):
    """Uniformly distributed random locations.

    ``n_groups`` splits the locations into that many groups; for synapse placement each group is a
    distinct presynaptic neuron.
    """

    title: ClassVar[str] = "Random Morphology Locations"

    def _make_points(self, morphology: morphio.Morphology) -> pd.DataFrame:
        locs = generate_neurite_locations_on(
            morphology,
            n_centers=1,
            n_per_center=self.number_of_locations,  # ty:ignore[invalid-argument-type]
            srcs_per_center=self.n_groups,  # ty:ignore[invalid-argument-type]
            center_path_distances_mean=0.0,
            center_path_distances_sd=0.0,
            max_dist_from_center=None,  # ty:ignore[invalid-argument-type]
            lst_section_types=self.section_types,  # ty:ignore[invalid-argument-type]
            seed=self.random_seed,  # ty:ignore[invalid-argument-type]
        ).drop(columns=[_CEN_IDX])
        return locs

    def _check_parameter_values(self) -> None:
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.number_of_locations, list) and self.number_of_locations <= 0:
            msg = f"Number of locations: {self.number_of_locations} <= 0"
            raise ValueError(msg)
