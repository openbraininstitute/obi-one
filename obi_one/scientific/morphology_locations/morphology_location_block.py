import abc
from typing import Self

import morphio
from pydantic import Field, model_validator

from obi_one.core.block import Block

from .specified_morphology_locations import _CEN_IDX, generate_neurite_locations_on


class MorphologyLocationsBlock(Block, abc.ABC):
    """Base class representing parameterized locations on morphology skeletons."""

    random_seed: int | list[int] = Field(
        default=0, name="Random seed", description="Seed for the random generation of locations"
    )
    number_of_locations: int | list[int] = Field(
        default=1,
        name="Number of locations",
        description="Number of locations to generate on morphology",
    )
    section_types: tuple[int, ...] | list[tuple[int, ...]] | None = Field(
        default=None,
        name="Section types",
        description="Types of sections to generate locations on. 2: axon, 3: basal, 4: apical",
    )

    @abc.abstractmethod
    def _make_points(self, morphology: morphio.Morphology):
        """Returns a generated list of points for the morphology."""

    @abc.abstractmethod
    def _check_parameter_values(self):
        """Do specific checks on the validity of parameters."""

    @model_validator(mode="after")
    def check_parameter_values(self) -> Self:
        # Only check whenever list are resolved to individual objects
        self._check_parameter_values()
        return self

    def points_on(self, morphology: morphio.Morphology):
        self.enforce_no_lists()
        return self._make_points(morphology)


class RandomMorphologyLocations(MorphologyLocationsBlock):
    """Completely random locations without constraint."""

    def _make_points(self, morphology: morphio.Morphology):
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

    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.number_of_locations, list):
            assert self.number_of_locations > 0, "Number of locations must be at least one!"


class RandomGroupedMorphologyLocations(MorphologyLocationsBlock):
    """Completely random locations, but grouped into abstract groups."""

    n_groups: int | list[int] = Field(
        default=1,
        name="Number of groups",
        description="Number of groups of locations to \
            generate",
    )

    def _make_points(self, morphology: morphio.Morphology):
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

    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.n_groups, list):
            assert self.n_groups > 0, "Number of groups must be at least one!"


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

    def _make_points(self, morphology: morphio.Morphology):
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

    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.path_dist_mean, list):
            assert self.path_dist_mean >= 0.0, "Path distance mean must be non-negative!"

        if not isinstance(self.path_dist_tolerance, list):
            assert self.path_dist_tolerance >= 1.0, (
                "For numerical reasons, path distance tolerance must be at least 1.0!"
            )


class ClusteredMorphologyLocations(MorphologyLocationsBlock):
    """Clustered random locations."""

    n_clusters: int | list[int] = Field(
        name="Number of clusters", description="Number of location clusters to generate"
    )
    cluster_max_distance: float | list[float] = Field(
        name="Cluster maximum distance",
        description="Maximum distance in um of generated locations from the center of their \
            cluster",
    )

    def _make_points(self, morphology: morphio.Morphology):
        # FIXME: This rounds down. Could make missing points
        # in a second call to generate_neurite_locations_on
        n_per_cluster = int(self.number_of_locations / self.n_clusters)
        locs = generate_neurite_locations_on(
            morphology,
            n_centers=self.n_clusters,
            n_per_center=n_per_cluster,
            srcs_per_center=1,
            center_path_distances_mean=0.0,
            center_path_distances_sd=1e20,
            max_dist_from_center=self.cluster_max_distance,
            lst_section_types=self.section_types,
            seed=self.random_seed,
        ).drop(columns=[_CEN_IDX])
        return locs

    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.n_clusters, list):
            assert self.n_clusters >= 1, "Number of clusters must be at least one!"
            if not isinstance(self.number_of_locations, list):
                assert self.number_of_locations >= self.n_clusters, (
                    "Cannot make more clusters than locations!"
                )


class ClusteredGroupedMorphologyLocations(
    ClusteredMorphologyLocations, RandomGroupedMorphologyLocations
):
    """Clustered random locations, grouped in to conceptual groups."""

    def _make_points(self, morphology: morphio.Morphology):
        # FIXME: This rounds down. Could make missing points
        # in a second call to generate_neurite_locations_on
        n_per_cluster = int(self.number_of_locations / self.n_clusters)
        locs = generate_neurite_locations_on(
            morphology,
            n_centers=self.n_clusters,
            n_per_center=n_per_cluster,
            srcs_per_center=self.n_groups,
            center_path_distances_mean=0.0,
            center_path_distances_sd=1e20,
            max_dist_from_center=self.cluster_max_distance,
            lst_section_types=self.section_types,
            seed=self.random_seed,
        ).drop(columns=[_CEN_IDX])
        return locs

    def _check_parameter_values(self):
        super(ClusteredMorphologyLocations, self)._check_parameter_values()
        super(RandomGroupedMorphologyLocations, self)._check_parameter_values()


class ClusteredPathDistanceMorphologyLocations(ClusteredMorphologyLocations):
    """Clustered random locations around a specified path distance. Also creates
    groups within each cluster. This exposes the full possible complexity.
    """

    path_dist_mean: float | list[float] = Field(
        name="Path distance mean",
        description="Mean of a Gaussian, defined on soma path distance in um. Used to determine \
            locations.",
    )
    path_dist_sd: float | list[float] = Field(
        name="Path distance mean",
        description="SD of a Gaussian, defined on soma path distance in um. Used to determine \
            locations.",
    )
    n_groups_per_cluster: int | list[int] = Field(
        default=1,
        name="Number of groups per cluster",
        description="Number of conceptual groups per location cluster to generate",
    )

    def _make_points(self, morphology: morphio.Morphology):
        # FIXME: This rounds down. Could make missing points
        # in a second call to generate_neurite_locations_on
        n_per_cluster = int(self.number_of_locations / self.n_clusters)
        locs = generate_neurite_locations_on(
            morphology,
            n_centers=self.n_clusters,
            n_per_center=n_per_cluster,
            srcs_per_center=self.n_groups_per_cluster,
            center_path_distances_mean=self.path_dist_mean,
            center_path_distances_sd=self.path_dist_sd,
            max_dist_from_center=self.cluster_max_distance,
            lst_section_types=self.section_types,
            seed=self.random_seed,
        )
        return locs

    def _check_parameter_values(self):
        super()._check_parameter_values()
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.path_dist_mean, list):
            assert self.path_dist_mean >= 0.0, "Path distance mean must be non-negative!"

        if not isinstance(self.path_dist_sd, list):
            assert self.path_dist_sd >= 0.1, (
                "For numerical reasons, path distance standard deviation must be at least 0.1!"
            )

        if not isinstance(self.n_groups_per_cluster, list):
            assert self.n_groups_per_cluster >= 1, (
                "Number of groups per cluster must be at least 1!"
            )
