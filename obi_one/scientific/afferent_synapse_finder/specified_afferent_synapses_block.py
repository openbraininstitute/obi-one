import abc
from typing import Self

from pydantic import Field, model_validator

from obi_one.core.block import Block

from .find_specified_afferent_synapses import (
    morphology_and_pathdistance_calculator,
    all_syns_on,
    add_section_types,
    apply_filters,
    relevant_path_distances,
    select_minmax_distance,
    select_randomly,
    select_by_path_distance,
    select_clusters_by_max_distance,
    select_clusters_by_count
)


class AfferentSynapsesBlock(Block, abc.ABC):
    """Base class representing the selection of afferent synapses according to specs."""

    random_seed: int | list[int] = Field(
        default=0, name="Random seed", description="Seed for the random selection of synapses"
    )
    section_types: None | tuple[int, ...] | list[tuple[int, ...]] = Field(
        default=None,
        name="Section types",
        description="Valid types of sections for synapses. 2: axon, 3: basal, 4: apical",
    )
    pre_synapse_class: None | str | list[str] = Field(
        default=None,
        name="Synapse class",
        description="Valid synapse classes. EXC: excitatory synapses; INH: inhibitory synapses",
    )
    consider_nan_pass: bool | list[bool] = Field(
        default=True,
        name="Consider nan to pass",
        description="If False, synapses with no 'synapse_class' pass, else not."
    )
    pre_node_populations: None | tuple[str, ...] | list[tuple[str, ...]] = Field(
        default=None,
        name="Presynaptic populations",
        description="Names of presynaptic node populations to allow"
    )

    def gather_synapse_info(self, circ, node_population, node_id):
        prop_filters = {}
        node_props = []
        if self.pre_synapse_class is not None:
            prop_filters["synapse_class"] = self.pre_synapse_class
            node_props.append("synapse_class")
        if self.pre_node_populations is not None:
            prop_filters["source_population"] = list(self.pre_node_populations)
        if self.section_types is not None:
            prop_filters["afferent_section_type"] = list(self.section_types)

        morph, PD = morphology_and_pathdistance_calculator(circ, node_population, node_id)
        syns = all_syns_on(circ, node_population, node_id, node_props)
        add_section_types(syns, morph)
        drop_nan = not self.consider_nan_pass
        syns = apply_filters(syns, prop_filters, drop_nan=drop_nan)
        soma_pds, pw_pds = relevant_path_distances(PD, syns)
        return syns, soma_pds, pw_pds

    @abc.abstractmethod
    def _select_syns(self, *args):
        """Returns a generated list of points for the morphology."""

    @abc.abstractmethod
    def _check_parameter_values(self):
        """Do specific checks on the validity of parameters."""

    @model_validator(mode="after")
    def check_parameter_values(self) -> Self:
        # Only check whenever list are resolved to individual objects
        self._check_parameter_values()
        return self

    def synapses_on(self, circ, node_population, node_id):
        self.enforce_no_lists()
        args = self.gather_synapse_info(circ, node_population, node_id)
        return self._select_syns(*args)


class RandomlySelectedNumberOfSynapses(AfferentSynapsesBlock):
    """Completely random synapses without constraint"""
    n: int | list[int] = Field(
        default=1,
        name="Number of synapses",
        description="Number of synapses to pick",
    )

    def _select_syns(self, syns, *args):
        return select_randomly(syns, n=self.n, raise_insufficient=False)
        
    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.n, list):
            assert self.n > 0, "Number of synapses must be at least one!"

class RandomlySelectedFractionOfSynapses(AfferentSynapsesBlock):
    """Completely random synapses without constraint"""
    p: int | list[int] = Field(
        default=1.0,
        name="Fracton of synapses",
        description="Fracton of synapses to pick",
    )

    def _select_syns(self, syns, *args):
        return select_randomly(syns, p=self.p, raise_insufficient=False)
        
    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.p, list):
            assert self.p > 0, "Fraction of synapses must be > 0!"
            assert self.p <= 1.0, "Number of synapses must be <= 1.0!"

class PathDistanceConstrainedNumberOfSynapses(RandomlySelectedNumberOfSynapses):
    soma_pd_min: float | list[float] = Field(
        default=0.0,
        name="Minimum soma path distance",
        description="Minimum path distance in um to the soma for synapses"
    )
    soma_pd_max: float | list[float] = Field(
        default=1E12,
        name="Maximum soma path distance",
        description="Maximm path distance in um to the soma for synapses"
    )

    def _select_syns(self, syns, soma_pds, *args):
        return select_minmax_distance(syns, soma_pds,
                                      soma_pd_min=self.soma_pd_min,
                                      soma_pd_max=self.soma_pd_max,
                                      n=self.n, raise_insufficient=False)

class PathDistanceConstrainedFractionOfSynapses(RandomlySelectedFractionOfSynapses):
    soma_pd_min: float | list[float] = Field(
        default=0.0,
        name="Minimum soma path distance",
        description="Minimum path distance in um to the soma for synapses"
    )
    soma_pd_max: float | list[float] = Field(
        default=1E12,
        name="Maximum soma path distance",
        description="Maximm path distance in um to the soma for synapses"
    )

    def _select_syns(self, syns, soma_pds, *args):
        return select_minmax_distance(syns, soma_pds,
                                      soma_pd_min=self.soma_pd_min,
                                      soma_pd_max=self.soma_pd_max,
                                      n=self.p, raise_insufficient=False)

class PathDistanceWeightedNumberOfSynapses(RandomlySelectedNumberOfSynapses):
    soma_pd_mean: float | list[float] = Field(
        name="Mean soma path distance",
        description="Mean of a Gaussian for soma path distance in um for selecting synapses"
    )
    soma_pd_sd: float | list[float] = Field(
        name="SD for soma path distance",
        description="SD of a Gaussian for soma path distance in um for selecting synapses"
    )

    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.soma_pd_sd, list):
            assert self.soma_pd_sd > 0, "SD of Gaussian must be > 0!"
    
    def _select_syns(self, syns, soma_pds, *args):
        return select_by_path_distance(
            syns, soma_pds,
            soma_pd_mean=self.soma_pd_mean,
            soma_pd_sd=self.soma_pd_sd, n=self.n,
            raise_insufficient=False
        )

class PathDistanceWeightedFractionOfSynapses(RandomlySelectedFractionOfSynapses):
    soma_pd_mean: float | list[float] = Field(
        name="Mean soma path distance",
        description="Mean of a Gaussian for soma path distance in um for selecting synapses"
    )
    soma_pd_sd: float | list[float] = Field(
        name="SD for soma path distance",
        description="SD of a Gaussian for soma path distance in um for selecting synapses"
    )

    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.soma_pd_sd, list):
            assert self.soma_pd_sd > 0, "SD of Gaussian must be > 0!"
    
    def _select_syns(self, syns, soma_pds, *args):
        return select_by_path_distance(
            syns, soma_pds,
            soma_pd_mean=self.soma_pd_mean,
            soma_pd_sd=self.soma_pd_sd, n=self.p,
            raise_insufficient=False
        )

class ClusteredSynapsesByMaxDistance(AfferentSynapsesBlock):
    n_clusters: int | list[int] = Field(
        default=1,
        name="Number of clusters",
        description="Number of synapse clusters to find"
    )
    cluster_max_distance : float | list[float] = Field(
        name="Maximum cluster distance",
        description="Synapses within a cluster will be closer than this value from the cluster center (in um)"
    )

    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.n_clusters, list):
            assert self.n_clusters > 0, "Must generate at least one cluster!"
        if not isinstance(self.cluster_max_distance, list):
            assert self.cluster_max_distance >= 0, "Cluster distance must be >= 0"
    
    def _select_syns(self, syns, soma_pds, pw_pds):
        return select_clusters_by_max_distance(
            syns, soma_pds, pw_pds,
            n_clusters=self.n_clusters,
            cluster_max_distance=self.cluster_max_distance, 
            raise_insufficient=False
        )

class ClusteredSynapsesByCount(AfferentSynapsesBlock):
    n_clusters: int | list[int] = Field(
        default=1,
        name="Number of clusters",
        description="Number of synapse clusters to find"
    )
    n_per_cluster : int | list[int] = Field(
        name="Number of synapses per cluster",
        description="This number of synapses per cluster will be selected by proximity to a center synapse."
    )

    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.n_clusters, list):
            assert self.n_clusters > 0, "Must generate at least one cluster!"
        if not isinstance(self.n_per_cluster, list):
            assert self.n_per_cluster > 0, "Must select at least one synapse per cluster!"
    
    def _select_syns(self, syns, soma_pds, pw_pds):
        return select_clusters_by_count(
            syns, soma_pds, pw_pds,
            n_clusters=self.n_clusters,
            n_per_cluster=self.n_per_cluster,
            raise_insufficient=False
        )
    
class ClusteredPDSynapsesByMaxDistance(ClusteredSynapsesByMaxDistance):
    soma_pd_mean: float | list[float] = Field(
        name="Mean soma path distance",
        description="Mean of a Gaussian for soma path distance in um for selecting synapses"
    )
    soma_pd_sd: float | list[float] = Field(
        name="SD for soma path distance",
        description="SD of a Gaussian for soma path distance in um for selecting synapses"
    )

    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.soma_pd_sd, list):
            assert self.soma_pd_sd > 0, "SD of Gaussian must be > 0!"
    
    def _select_syns(self, syns, soma_pds, pw_pds):
        return select_clusters_by_max_distance(
            syns, soma_pds, pw_pds,
            n_clusters=self.n_clusters,
            cluster_max_distance=self.cluster_max_distance, 
            soma_pd_mean=self.soma_pd_mean,
            soma_pd_sd=self.soma_pd_sd,
            raise_insufficient=False
        )
    
class ClusteredPDSynapsesByCount(ClusteredSynapsesByCount):
    soma_pd_mean: float | list[float] = Field(
        name="Mean soma path distance",
        description="Mean of a Gaussian for soma path distance in um for selecting synapses"
    )
    soma_pd_sd: float | list[float] = Field(
        name="SD for soma path distance",
        description="SD of a Gaussian for soma path distance in um for selecting synapses"
    )

    def _check_parameter_values(self):
        # Only check whenever list are resolved to individual objects
        if not isinstance(self.soma_pd_sd, list):
            assert self.soma_pd_sd > 0, "SD of Gaussian must be > 0!"
    
    def _select_syns(self, syns, soma_pds, pw_pds):
        return select_clusters_by_count(
            syns, soma_pds, pw_pds,
            n_clusters=self.n_clusters,
            n_per_cluster=self.n_per_cluster,
            soma_pd_mean=self.soma_pd_mean,
            soma_pd_sd=self.soma_pd_sd,
            raise_insufficient=False
        )
