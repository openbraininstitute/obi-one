import math
from typing import Annotated, ClassVar, cast

import morphio
import pandas as pd
from pydantic import Field, NonNegativeFloat, PositiveInt

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.morphology_locations.base import (
    MorphologyLocationsBlock,
)
from obi_one.scientific.blocks.morphology_locations.random import (
    RandomGroupedMorphologyLocations,
)
from obi_one.scientific.library.morphology_locations import (
    _CEN_IDX,
    generate_neurite_locations_on,
)

_MIN_PD_SD = 0.1
PathDistanceStandardDeviationParameter = Annotated[float, Field(ge=_MIN_PD_SD)]


class ClusteredMorphologyLocations(MorphologyLocationsBlock):
    """Clustered locations with cluster centers randomly distributed across selected neurites."""

    title: ClassVar[str] = "Random Clustered Morphology Locations"

    n_clusters: PositiveInt | list[PositiveInt] = Field(
        default=5,
        title="Number of Clusters",
        description=(
            "Number of randomly placed clusters to generate. The total number of locations is "
            "divided across these clusters."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )
    cluster_max_distance: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=50.0,
        title="Maximum Distance from Cluster Center",
        description=(
            "Maximum soma path distance between each generated location and its cluster center. "
            "Locations are sampled uniformly from valid morphology intervals within this distance."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )

    def _make_points(self, morphology: morphio.Morphology) -> pd.DataFrame:
        count = cast("int", self.number_of_locations)
        n_clusters = cast("int", self.n_clusters)
        n_per_cluster = math.ceil(count / n_clusters)
        locs = generate_neurite_locations_on(
            morphology,
            n_centers=n_clusters,
            n_per_center=n_per_cluster,
            srcs_per_center=1,
            center_path_distances_mean=0.0,
            center_path_distances_sd=1e20,
            max_dist_from_center=self.cluster_max_distance,  # ty:ignore[invalid-argument-type]
            lst_section_types=self.section_types,  # ty:ignore[invalid-argument-type]
            seed=self.random_seed,  # ty:ignore[invalid-argument-type]
        ).drop(columns=[_CEN_IDX])
        locs = locs.iloc[:count]
        return locs

    def _check_parameter_values(self) -> None:
        # Only check whenever lists are resolved to individual objects
        if (
            not isinstance(self.n_clusters, list)
            and not isinstance(self.number_of_locations, list)
            and self.number_of_locations < self.n_clusters
        ):
            msg = (
                f"Number of locations: {self.number_of_locations} "
                f"< number of clusters: {self.n_clusters}"
            )
            raise ValueError(msg)


class ClusteredGroupedMorphologyLocations(
    ClusteredMorphologyLocations, RandomGroupedMorphologyLocations
):
    """Clustered random locations, grouped in to conceptual groups."""

    title: ClassVar[str] = "Clustered Grouped Morphology Locations"

    def _make_points(self, morphology: morphio.Morphology) -> pd.DataFrame:
        count = cast("int", self.number_of_locations)
        n_clusters = cast("int", self.n_clusters)
        n_per_cluster = math.ceil(count / n_clusters)
        locs = generate_neurite_locations_on(
            morphology,
            n_centers=n_clusters,
            n_per_center=n_per_cluster,
            srcs_per_center=self.n_groups,  # ty:ignore[invalid-argument-type]
            center_path_distances_mean=0.0,
            center_path_distances_sd=1e20,
            max_dist_from_center=self.cluster_max_distance,  # ty:ignore[invalid-argument-type]
            lst_section_types=self.section_types,  # ty:ignore[invalid-argument-type]
            seed=self.random_seed,  # ty:ignore[invalid-argument-type]
        ).drop(columns=[_CEN_IDX])
        locs = locs.iloc[:count]
        return locs

    def _check_parameter_values(self) -> None:
        super(ClusteredMorphologyLocations, self)._check_parameter_values()
        super(RandomGroupedMorphologyLocations, self)._check_parameter_values()


class ClusteredPathDistanceMorphologyLocations(ClusteredMorphologyLocations):
    """Locations uniformly sampled within clusters whose centers are normally distributed
    around a specified soma path distance.
    """

    title: ClassVar[str] = "Clustered Path Distance Morphology Locations"

    path_dist_mean: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=100.0,
        title="Cluster Path Distance Sampling Mean",
        description=("Target soma path distance used to bias where cluster centers are selected."),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    path_dist_sd: (
        PathDistanceStandardDeviationParameter | list[PathDistanceStandardDeviationParameter]
    ) = Field(
        default=50.0,
        title="Cluster Path Distance Standard Deviation",
        description=(
            "Standard deviation of the soma path-distance distribution used to select "
            "cluster centers."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICROMETERS,
        },
    )
    n_groups_per_cluster: PositiveInt | list[PositiveInt] = Field(
        default=1,
        title="Groups per Cluster",
        description=("Number of conceptual groups to assign within each generated cluster."),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    def _make_points(self, morphology: morphio.Morphology) -> pd.DataFrame:
        count = cast("int", self.number_of_locations)
        n_clusters = cast("int", self.n_clusters)
        n_per_cluster = math.ceil(count / n_clusters)
        locs = generate_neurite_locations_on(
            morphology,
            n_centers=n_clusters,
            n_per_center=n_per_cluster,
            srcs_per_center=self.n_groups_per_cluster,  # ty:ignore[invalid-argument-type]
            center_path_distances_mean=self.path_dist_mean,  # ty:ignore[invalid-argument-type]
            center_path_distances_sd=self.path_dist_sd,  # ty:ignore[invalid-argument-type]
            max_dist_from_center=self.cluster_max_distance,  # ty:ignore[invalid-argument-type]
            lst_section_types=self.section_types,  # ty:ignore[invalid-argument-type]
            seed=self.random_seed,  # ty:ignore[invalid-argument-type]
        )
        return locs.iloc[:count]

    def _check_parameter_values(self) -> None:
        super()._check_parameter_values()
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.path_dist_mean, list):  # ruff: ignore[collapsible-if]
            if self.path_dist_mean < 0:
                msg = f"Path distance mean: {self.path_dist_mean} < 0"
                raise ValueError(msg)

        if not isinstance(self.path_dist_sd, list):  # ruff: ignore[collapsible-if]
            if self.path_dist_sd < _MIN_PD_SD:
                msg = f"Path distance std: {self.path_dist_sd} < {_MIN_PD_SD} (numerical stability)"
                raise ValueError(msg)

        if not isinstance(self.n_groups_per_cluster, list):  # ruff: ignore[collapsible-if]
            if self.n_groups_per_cluster < 1:
                msg = f"Number of groups per cluster: {self.n_groups_per_cluster} < 1"
                raise ValueError(msg)
