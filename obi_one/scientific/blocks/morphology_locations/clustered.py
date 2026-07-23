import morphio
import pandas  # noqa: ICN001
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.morphology_locations.base import MorphologyLocationsBlock
from obi_one.scientific.blocks.morphology_locations.random import (
    RandomGroupedMorphologyLocations,
)
from obi_one.scientific.library.morphology_locations import (
    _CEN_IDX,
    generate_neurite_locations_on,
)

_MIN_PD_SD = 0.1


class ClusteredMorphologyLocations(MorphologyLocationsBlock):
    """Clustered random locations."""

    n_clusters: int | list[int] = Field(
        title="Number of clusters",
        description="Number of location clusters to generate",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )
    cluster_max_distance: float | list[float] = Field(
        title="Cluster maximum distance",
        description="Maximum distance in um of generated locations from the center of their \
            cluster",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    def _make_points(self, morphology: morphio.Morphology) -> pandas.DataFrame:
        # TODO: This rounds down. Could make missing points
        # in a second call to generate_neurite_locations_on
        n_per_cluster = int(self.number_of_locations / self.n_clusters)  # ty:ignore[unsupported-operator]
        locs = generate_neurite_locations_on(
            morphology,
            n_centers=self.n_clusters,  # ty:ignore[invalid-argument-type]
            n_per_center=n_per_cluster,
            srcs_per_center=1,
            center_path_distances_mean=0.0,
            center_path_distances_sd=1e20,
            max_dist_from_center=self.cluster_max_distance,  # ty:ignore[invalid-argument-type]
            lst_section_types=self.section_types,  # ty:ignore[invalid-argument-type]
            seed=self.random_seed,  # ty:ignore[invalid-argument-type]
        ).drop(columns=[_CEN_IDX])
        return locs

    def _check_parameter_values(self) -> None:
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.n_clusters, list):
            if self.n_clusters < 1:
                msg = f"Number of clusters {self.n_clusters} < 1"
                raise ValueError(msg)
            if not isinstance(self.number_of_locations, list):  # noqa: SIM102
                if self.number_of_locations < self.n_clusters:
                    msg = f"Number of locations: {self.number_of_locations} \
                        < number of clusters: {self.n_clusters}"
                    raise ValueError(msg)


class ClusteredGroupedMorphologyLocations(
    ClusteredMorphologyLocations, RandomGroupedMorphologyLocations
):
    """Clustered random locations, grouped in to conceptual groups."""

    def _make_points(self, morphology: morphio.Morphology) -> pandas.DataFrame:
        # TODO: This rounds down. Could make missing points
        # in a second call to generate_neurite_locations_on
        n_per_cluster = int(self.number_of_locations / self.n_clusters)  # ty:ignore[unsupported-operator]
        locs = generate_neurite_locations_on(
            morphology,
            n_centers=self.n_clusters,  # ty:ignore[invalid-argument-type]
            n_per_center=n_per_cluster,
            srcs_per_center=self.n_groups,  # ty:ignore[invalid-argument-type]
            center_path_distances_mean=0.0,
            center_path_distances_sd=1e20,
            max_dist_from_center=self.cluster_max_distance,  # ty:ignore[invalid-argument-type]
            lst_section_types=self.section_types,  # ty:ignore[invalid-argument-type]
            seed=self.random_seed,  # ty:ignore[invalid-argument-type]
        ).drop(columns=[_CEN_IDX])
        return locs

    def _check_parameter_values(self) -> None:
        super(ClusteredMorphologyLocations, self)._check_parameter_values()
        super(RandomGroupedMorphologyLocations, self)._check_parameter_values()


class ClusteredPathDistanceMorphologyLocations(ClusteredMorphologyLocations):
    """Clustered random locations around a specified path distance. Also creates
    groups within each cluster. This exposes the full possible complexity.
    """

    path_dist_mean: float | list[float] = Field(
        title="Path distance mean",
        description="Mean of a Gaussian, defined on soma path distance in um. Used to determine \
            locations.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )
    path_dist_sd: float | list[float] = Field(
        title="Path distance mean",
        description="SD of a Gaussian, defined on soma path distance in um. Used to determine \
            locations.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )
    n_groups_per_cluster: int | list[int] = Field(
        default=1,
        title="Number of groups per cluster",
        description="Number of conceptual groups per location cluster to generate",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    def _make_points(self, morphology: morphio.Morphology) -> pandas.DataFrame:
        # TODO: This rounds down. Could make missing points
        # in a second call to generate_neurite_locations_on
        n_per_cluster = int(self.number_of_locations / self.n_clusters)  # ty:ignore[unsupported-operator]
        locs = generate_neurite_locations_on(
            morphology,
            n_centers=self.n_clusters,  # ty:ignore[invalid-argument-type]
            n_per_center=n_per_cluster,
            srcs_per_center=self.n_groups_per_cluster,  # ty:ignore[invalid-argument-type]
            center_path_distances_mean=self.path_dist_mean,  # ty:ignore[invalid-argument-type]
            center_path_distances_sd=self.path_dist_sd,  # ty:ignore[invalid-argument-type]
            max_dist_from_center=self.cluster_max_distance,  # ty:ignore[invalid-argument-type]
            lst_section_types=self.section_types,  # ty:ignore[invalid-argument-type]
            seed=self.random_seed,  # ty:ignore[invalid-argument-type]
        )
        return locs

    def _check_parameter_values(self) -> None:
        super()._check_parameter_values()
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.path_dist_mean, list):  # noqa: SIM102
            if self.path_dist_mean < 0:
                msg = f"Path distance mean: {self.path_dist_mean} < 0"
                raise ValueError(msg)

        if not isinstance(self.path_dist_sd, list):  # noqa: SIM102
            if self.path_dist_sd < _MIN_PD_SD:
                msg = f"Path distance std: {self.path_dist_sd} < {_MIN_PD_SD} (numerical stability)"
                raise ValueError(msg)

        if not isinstance(self.n_groups_per_cluster, list):  # noqa: SIM102
            if self.n_groups_per_cluster < 1:
                msg = f"Number of groups per cluster: {self.n_groups_per_cluster} < 1"
                raise ValueError(msg)
