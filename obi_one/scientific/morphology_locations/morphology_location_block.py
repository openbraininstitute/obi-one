import abc
import json
import os
from typing import Annotated, Self

import bluepysnap as snap
import numpy as np
from pydantic import Field, model_validator

from obi_one.core.block import Block
from .specified_morphology_locations import (
    generate_neurite_locations_on,
    _CEN_IDX,
    _PRE_IDX
)


class MorphologyLocations(Block, abc.ABC):
    """Base class representing parameterized locations on morphology skeletons."""

    name: None | Annotated[str, Field(min_length=1)] = None
    description: None | Annotated[str, Field(min_length=1)] = None
    random_seed: int | list[int] = 0
    number_of_locations: int | list[int] = 1
    section_types: None | tuple[int, ...] | list[tuple[int, ...]] = None

    @abc.abstractmethod
    def _make_points(self, morphology):
        """Returns a generated list of points for the morphology."""
    
    @abc.abstractmethod
    def _check_parameter_values(self):
        """Do specific checks on the validity of parameters."""
    
    @model_validator(mode="after")
    def check_parameter_values(self) -> Self:
        # Only check whenever list are resolved to individual objects
        self._check_parameter_values()
        return self
    
    def points_on(self, morphology):
        self.enforce_no_lists()
        return self._make_points(morphology)

class RandomMorphologyLocations(MorphologyLocations):
    """Completely random locations without constraint"""

    def _make_points(self, morphology):
        locs = generate_neurite_locations_on(
            morphology,
            1,
            self.number_of_locations,
            1,
            0.0,
            0.0,
            None,
            lst_section_types=self.section_types,
            seed=self.random_seed
        ).drop(columns=[_CEN_IDX, _PRE_IDX])
        return locs
    
    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.number_of_locations, list):
            assert self.number_of_locations > 0, (
                "Number of locations must be at least one!"
            )

class RandomGroupedMorphologyLocations(MorphologyLocations):
    """Completely random locations, but grouped into abstract groups"""
    n_groups: int | list[int] = 1

    def _make_points(self, morphology):
        locs = generate_neurite_locations_on(
            morphology,
            1,
            self.number_of_locations,
            self.n_groups,
            0.0,
            0.0,
            None,
            lst_section_types=self.section_types,
            seed=self.random_seed
        ).drop(columns=[_CEN_IDX])
        return locs
    
    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.n_groups, list):
            assert self.n_groups > 0, (
                "Number of groups must be at least one!"
            )

class PathDistanceMorphologyLocations(MorphologyLocations):
    """Locations around a specified path distance"""
    path_dist_mean: float | list[float]
    path_dist_tolerance: float | list[float]

    def _make_points(self, morphology):
        locs = generate_neurite_locations_on(
            morphology,
            self.number_of_locations,
            1,
            1,
            self.path_dist_mean,
            0.1 * self.path_dist_tolerance,
            0.9 * self.path_dist_tolerance,
            lst_section_types=self.section_types,
            seed=self.random_seed
        ).drop(columns=[_CEN_IDX, _PRE_IDX])
        return locs
    
    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.path_dist_mean, list):
            assert self.path_dist_mean >= 0.0, (
                "Path distance mean must be non-negative!"
            )

        if not isinstance(self.path_dist_tolerance, list):
            assert self.path_dist_tolerance >= 1.0, (
                "For numerical reasons, path distance tolerance must be at least 1.0!"
            )

class ClusteredMorphologyLocations(MorphologyLocations):
    """Clustered random locations"""
    n_clusters: int | list[int]
    cluster_max_distance: float | list[float]

    def _make_points(self, morphology):
        # FIXME: This rounds down. Could make missing points
        # in a second call to generate_neurite_locations_on
        n_per_cluster = int(self.number_of_locations / self.n_clusters)
        locs = generate_neurite_locations_on(
            morphology,
            self.n_clusters,
            n_per_cluster,
            1,
            0.0,
            1E20,
            self.cluster_max_distance,
            lst_section_types=self.section_types,
            seed=self.random_seed
        ).drop(columns=[_PRE_IDX])
        return locs
    
    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.n_clusters, list):
            assert self.n_clusters >= 1, (
                "Number of clusters must be at least one!"
            )
            if not isinstance(self.number_of_locations, list):
                assert self.number_of_locations >= self.n_clusters, (
                    "Cannot make more clusters than locations!"
                )

class ClusteredGroupedMorphologyLocations(ClusteredMorphologyLocations, RandomGroupedMorphologyLocations):
    """Clustered random locations, grouped in to conceptual groups."""
    
    def _make_points(self, morphology):
        # FIXME: This rounds down. Could make missing points
        # in a second call to generate_neurite_locations_on
        n_per_cluster = int(self.number_of_locations / self.n_clusters)
        locs = generate_neurite_locations_on(
            morphology,
            self.n_clusters,
            n_per_cluster,
            self.n_groups,
            0.0,
            1E20,
            self.cluster_max_distance,
            lst_section_types=self.section_types,
            seed=self.random_seed
        ).drop(columns=[_PRE_IDX])
        return locs
    
    def _check_parameter_values(self):
        super(ClusteredMorphologyLocations, self)._check_parameter_values()
        super(RandomGroupedMorphologyLocations, self)._check_parameter_values()

class ClusteredPathDistanceMorphologyLocations(ClusteredMorphologyLocations):
    """Clustered random locations around a specified path distance. Also creates
    groups within each cluster. This exposes the full possible complexity."""
    path_dist_mean: float | list[float]
    path_dist_sd: float | list[float]
    n_groups_per_cluster: int | list[int] = 1

    def _make_points(self, morphology):
        # FIXME: This rounds down. Could make missing points
        # in a second call to generate_neurite_locations_on
        n_per_cluster = int(self.number_of_locations / self.n_clusters)
        locs = generate_neurite_locations_on(
            morphology,
            self.n_clusters,
            n_per_cluster,
            self.n_groups_per_cluster,
            self.path_dist_mean,
            self.path_dist_sd,
            self.cluster_max_distance,
            lst_section_types=self.section_types,
            seed=self.random_seed
        )
        return locs
    
    def _check_parameter_values(self):
        super()._check_parameter_values()
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.path_dist_mean, list):
            assert self.path_dist_mean >= 0.0, (
                "Path distance mean must be non-negative!"
            )

        if not isinstance(self.path_dist_sd, list):
            assert self.path_dist_sd >= 0.1, (
                "For numerical reasons, path distance standard deviation must be at least 0.1!"
            )
        
        if not isinstance(self.n_groups_per_cluster, list):
            assert self.n_groups_per_cluster >= 1, (
                "Number of groups per cluster must be at least 1!"
            )
