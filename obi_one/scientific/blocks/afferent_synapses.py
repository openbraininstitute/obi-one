import abc
from typing import Self

import bluepysnap as snap
import numpy  # noqa: ICN001
import pandas  # noqa: ICN001
from pydantic import Field, model_validator

from obi_one.core.block import Block
from obi_one.scientific.library.find_afferent_synapses import (
    add_section_types,
    all_syns_on,
    apply_filters,
    merge_multiple_syns_per_connection,
    morphology_and_pathdistance_calculator,
    relevant_path_distances,
    select_by_path_distance,
    select_clusters_by_count,
    select_clusters_by_max_distance,
    select_minmax_distance,
    select_randomly,
)


class AfferentSynapsesBlock(Block, abc.ABC):
    """Base class representing the selection of afferent synapses according to specs."""

    random_seed: int | list[int] = Field(
        default=0, name="Random seed", description="Seed for the random selection of synapses"
    )
    section_types: tuple[int, ...] | list[tuple[int, ...]] | None = Field(
        default=None,
        name="Section types",
        description="Valid types of sections for synapses. 2: axon, 3: basal, 4: apical",
    )
    pre_synapse_class: str | list[str] | None = Field(
        default=None,
        name="Synapse class",
        description="Valid synapse classes. EXC: excitatory synapses; INH: inhibitory synapses",
    )
    consider_nan_pass: bool | list[bool] = Field(
        default=True,
        name="Consider nan to pass",
        description="If False, synapses with no 'synapse_class' pass, else not.",
    )
    pre_node_populations: tuple[str, ...] | list[tuple[str, ...]] | None = Field(
        default=None,
        name="Presynaptic populations",
        description="Names of presynaptic node populations to allow",
    )
    merge_multiple_syns_con: bool | list[bool] = Field(
        default=False,
        name="Merge multiple synapses per connection",
        description="""
        If True, multiple synapses from the same source neuron are merged by averaging.
        In this mode, it is not individual synapses that are selected, but presynaptic neurons.
        Where, if a neuron is selected, it is implied that all its synapses onto the target
        neuron are to be considered as selected.
        """,
    )

    def gather_synapse_info(
        self, circ: snap.Circuit, node_population: str, node_id: int
    ) -> tuple[pandas.DataFrame, numpy.ndarray, numpy.ndarray]:
        prop_filters = {}
        node_props = []
        if self.pre_synapse_class is not None:
            prop_filters["synapse_class"] = self.pre_synapse_class
            node_props.append("synapse_class")
        if self.pre_node_populations is not None:
            prop_filters["source_population"] = list(self.pre_node_populations)
        if self.section_types is not None:
            prop_filters["afferent_section_type"] = list(self.section_types)

        morph, PD = morphology_and_pathdistance_calculator(circ, node_population, node_id)  # noqa: N806
        syns = all_syns_on(circ, node_population, node_id, node_props)
        add_section_types(syns, morph)
        drop_nan = not self.consider_nan_pass
        syns = apply_filters(syns, prop_filters, drop_nan=drop_nan)
        soma_pds, pw_pds = relevant_path_distances(PD, syns)
        if self.merge_multiple_syns_con:
            syns, soma_pds, pw_pds = merge_multiple_syns_per_connection(syns, soma_pds, pw_pds)
        return syns, soma_pds, pw_pds

    @abc.abstractmethod
    def _select_syns(self, *args) -> pandas.DataFrame:
        """Returns a generated list of points for the morphology."""

    @abc.abstractmethod
    def _check_parameter_values(self) -> None:
        """Do specific checks on the validity of parameters."""

    @model_validator(mode="after")
    def check_parameter_values(self) -> Self:
        # Only check whenever list are resolved to individual objects
        self._check_parameter_values()
        return self

    def synapses_on(
        self, circ: snap.Circuit, node_population: str, node_id: int
    ) -> pandas.DataFrame:
        self.enforce_no_multi_param()
        numpy.random.seed(self.random_seed)  # noqa: NPY002
        args = self.gather_synapse_info(circ, node_population, node_id)
        return self._select_syns(*args)


class RandomlySelectedNumberOfSynapses(AfferentSynapsesBlock):
    """Completely random synapses without constraint.
    Specified number picked without bias.
    """

    n: int | list[int] = Field(
        default=1,
        name="Number of synapses",
        description="Number of synapses to pick",
    )

    def _select_syns(self, syns: pandas.DataFrame, *args) -> pandas.DataFrame:  # noqa: ARG002
        return select_randomly(syns, n=self.n, raise_insufficient=False)

    def _check_parameter_values(self) -> None:
        if (not isinstance(self.n, list)) and (self.n <= 0):
            msg = f"Number of synapses {self.n} <= 0"
            raise ValueError(msg)


class RandomlySelectedFractionOfSynapses(AfferentSynapsesBlock):
    """Completely random synapses without constraint.
    Each picked with specified probability.
    """

    p: int | list[int] = Field(
        default=1.0,
        name="Fracton of synapses",
        description="Fracton of synapses to pick",
    )

    def _select_syns(self, syns: pandas.DataFrame, *args) -> pandas.DataFrame:  # noqa: ARG002
        return select_randomly(syns, p=self.p, raise_insufficient=False)

    def _check_parameter_values(self) -> None:
        if not isinstance(self.p, list) and ((self.p <= 0) or (self.p > 1.0)):
            msg = f"p: {self.p} should be > 0 and <= 1"
            raise ValueError(msg)


class PathDistanceConstrainedNumberOfSynapses(RandomlySelectedNumberOfSynapses):
    """Pick from synapses between specified minimum and maximum path distances from the soma.
    Specified number of synapses within the path distance interval are picked without bias.
    """

    soma_pd_min: float | list[float] = Field(
        default=0.0,
        name="Minimum soma path distance",
        description="Minimum path distance in um to the soma for synapses",
    )
    soma_pd_max: float | list[float] = Field(
        default=1e12,
        name="Maximum soma path distance",
        description="Maximm path distance in um to the soma for synapses",
    )

    def _select_syns(
        self,
        syns: pandas.DataFrame,
        soma_pds: numpy.ndarray,
        *args,  # noqa: ARG002
    ) -> pandas.DataFrame:
        return select_minmax_distance(
            syns,
            soma_pds,
            soma_pd_min=self.soma_pd_min,
            soma_pd_max=self.soma_pd_max,
            n=self.n,
            raise_insufficient=False,
        )


class PathDistanceConstrainedFractionOfSynapses(RandomlySelectedFractionOfSynapses):
    """Pick from synapses between specified minimum and maximum path distances from the soma.
    From the synapses within the path distance interval a specified fractio is picked.
    """

    soma_pd_min: float | list[float] = Field(
        default=0.0,
        name="Minimum soma path distance",
        description="Minimum path distance in um to the soma for synapses",
    )
    soma_pd_max: float | list[float] = Field(
        default=1e12,
        name="Maximum soma path distance",
        description="Maximm path distance in um to the soma for synapses",
    )

    def _select_syns(
        self,
        syns: pandas.DataFrame,
        soma_pds: numpy.ndarray,
        *args,  # noqa: ARG002
    ) -> pandas.DataFrame:
        return select_minmax_distance(
            syns,
            soma_pds,
            soma_pd_min=self.soma_pd_min,
            soma_pd_max=self.soma_pd_max,
            n=self.p,
            raise_insufficient=False,
        )


class PathDistanceWeightedNumberOfSynapses(RandomlySelectedNumberOfSynapses):
    """Pick synapses with path distance-dependent bias. A specified number of synapses
    is picked, with synapses close to a specified path distance from the soma being
    more likely to be selected. The bias is expressed by a Gaussian mean and std.
    """

    soma_pd_mean: float | list[float] = Field(
        name="Mean soma path distance",
        description="Mean of a Gaussian for soma path distance in um for selecting synapses",
    )
    soma_pd_sd: float | list[float] = Field(
        name="SD for soma path distance",
        description="SD of a Gaussian for soma path distance in um for selecting synapses",
    )

    def _check_parameter_values(self) -> None:
        if (not isinstance(self.soma_pd_sd, list)) and (self.soma_pd_sd <= 0):
            msg = f"Soma path distance SD: {self.soma_pd_sd} should be > 0"
            raise ValueError(msg)

    def _select_syns(
        self,
        syns: pandas.DataFrame,
        soma_pds: numpy.ndarray,
        *args,  # noqa: ARG002
    ) -> pandas.DataFrame:
        return select_by_path_distance(
            syns,
            soma_pds,
            soma_pd_mean=self.soma_pd_mean,
            soma_pd_sd=self.soma_pd_sd,
            n=self.n,
            raise_insufficient=False,
        )


class PathDistanceWeightedFractionOfSynapses(RandomlySelectedFractionOfSynapses):
    """Pick synapses with path distance-dependent bias. A specified fraction of all synapses
    is picked, with synapses close to a specified path distance from the soma being
    more likely to be selected. The bias is expressed by a Gaussian mean and std.
    """

    soma_pd_mean: float | list[float] = Field(
        name="Mean soma path distance",
        description="Mean of a Gaussian for soma path distance in um for selecting synapses",
    )
    soma_pd_sd: float | list[float] = Field(
        name="SD for soma path distance",
        description="SD of a Gaussian for soma path distance in um for selecting synapses",
    )

    def _check_parameter_values(self) -> None:
        if (not isinstance(self.soma_pd_sd, list)) and self.soma_pd_sd <= 0:
            msg = f"Soma path distance SD: {self.soma_pd_sd} should be > 0"
            raise ValueError(msg)

    def _select_syns(
        self,
        syns: pandas.DataFrame,
        soma_pds: numpy.ndarray,
        *args,  # noqa: ARG002
    ) -> pandas.DataFrame:
        return select_by_path_distance(
            syns,
            soma_pds,
            soma_pd_mean=self.soma_pd_mean,
            soma_pd_sd=self.soma_pd_sd,
            n=self.p,
            raise_insufficient=False,
        )


class ClusteredSynapsesByMaxDistance(AfferentSynapsesBlock):
    """Pick clusters of synapses. A cluster in this context comprises all synapses
    closer than a maximum path distance to a synapse that has been picked as a
    cluster center. The center is picked randomly without bias.
    """

    n_clusters: int | list[int] = Field(
        default=1, name="Number of clusters", description="Number of synapse clusters to find"
    )
    cluster_max_distance: float | list[float] = Field(
        name="Maximum distance of synapses from cluster center",
        description="Synapses within a cluster will be closer than this value\
            from the cluster center (in um)",
    )

    def _check_parameter_values(self) -> None:
        if (not isinstance(self.n_clusters, list)) and (self.n_clusters <= 0):
            msg = f"Number of clusters: {self.n_clusters} should be > 0!"
            raise ValueError(msg)
        if (not isinstance(self.cluster_max_distance, list)) and (self.cluster_max_distance < 0):
            msg = f"Cluster distance: {self.cluster_max_distance} should be >= 0!"
            raise ValueError(msg)

    def _select_syns(
        self, syns: pandas.DataFrame, soma_pds: numpy.ndarray, pw_pds: numpy.ndarray
    ) -> pandas.DataFrame:
        return select_clusters_by_max_distance(
            syns,
            soma_pds,
            pw_pds,
            n_clusters=self.n_clusters,
            cluster_max_distance=self.cluster_max_distance,
            raise_insufficient=False,
        )


class ClusteredSynapsesByCount(AfferentSynapsesBlock):
    """Pick clusters of synapses. A cluster in this context comprises
    n_per_cluster synapses that are closest in path distance to a synapse that
    has been picked as a cluster center.
    The center is picked randomly without bias.
    """

    n_clusters: int | list[int] = Field(
        default=1, name="Number of clusters", description="Number of synapse clusters to find"
    )
    n_per_cluster: int | list[int] = Field(
        name="Number of synapses per cluster",
        description="This number of synapses per cluster will be selected\
            by proximity to a center synapse.",
    )

    def _check_parameter_values(self) -> None:
        if (not isinstance(self.n_clusters, list)) and (self.n_clusters <= 0):
            msg = f"Number of clusters: {self.n_clusters} should be > 0!"
            raise ValueError(msg)
        if (not isinstance(self.n_per_cluster, list)) and (self.n_per_cluster <= 0):
            msg = f"Number of synapses per cluster: {self.n_per_cluster} should be > 0!"
            raise ValueError(msg)

    def _select_syns(
        self, syns: pandas.DataFrame, soma_pds: numpy.ndarray, pw_pds: numpy.ndarray
    ) -> pandas.DataFrame:
        return select_clusters_by_count(
            syns,
            soma_pds,
            pw_pds,
            n_clusters=self.n_clusters,
            n_per_cluster=self.n_per_cluster,
            raise_insufficient=False,
        )


class ClusteredPDSynapsesByMaxDistance(ClusteredSynapsesByMaxDistance):
    """Pick clusters of synapses. A cluster in this context comprises all synapses
    closer than a maximum path distance to a synapse that has been picked as a
    cluster center.
    The center is picked with a bias that depends on path distance to the soma.
    That is, synapse close to a specified path distance are more likely to be
    selected.
    """

    soma_pd_mean: float | list[float] = Field(
        name="Mean soma path distance",
        description="Mean of a Gaussian for soma path distance in um for selecting synapses",
    )
    soma_pd_sd: float | list[float] = Field(
        name="SD for soma path distance",
        description="SD of a Gaussian for soma path distance in um for selecting synapses",
    )

    def _check_parameter_values(self) -> None:
        if (not isinstance(self.soma_pd_sd, list)) and (self.soma_pd_sd <= 0):
            msg = f"Soma path distance SD: {self.soma_pd_sd} should be > 0!"
            raise ValueError(msg)

    def _select_syns(
        self, syns: pandas.DataFrame, soma_pds: numpy.ndarray, pw_pds: numpy.ndarray
    ) -> pandas.DataFrame:
        return select_clusters_by_max_distance(
            syns,
            soma_pds,
            pw_pds,
            n_clusters=self.n_clusters,
            cluster_max_distance=self.cluster_max_distance,
            soma_pd_mean=self.soma_pd_mean,
            soma_pd_sd=self.soma_pd_sd,
            raise_insufficient=False,
        )


class ClusteredPDSynapsesByCount(ClusteredSynapsesByCount):
    """Pick clusters of synapses. A cluster in this context comprises
    n_per_cluster synapses that are closest in path distance to a synapse that
    has been picked as a cluster center.
    The center is picked with a bias that depends on path distance to the soma.
    That is, synapse close to a specified path distance are more likely to be
    selected.
    """

    soma_pd_mean: float | list[float] = Field(
        name="Mean soma path distance",
        description="Mean of a Gaussian for soma path distance in um for selecting synapses",
    )
    soma_pd_sd: float | list[float] = Field(
        name="SD for soma path distance",
        description="SD of a Gaussian for soma path distance in um for selecting synapses",
    )

    def _check_parameter_values(self) -> None:
        if (not isinstance(self.soma_pd_sd, list)) and (self.soma_pd_sd <= 0):
            msg = f"Soma path distance SD: {self.soma_pd_sd} should be > 0!"
            raise ValueError(msg)

    def _select_syns(
        self, syns: pandas.DataFrame, soma_pds: numpy.ndarray, pw_pds: numpy.ndarray
    ) -> pandas.DataFrame:
        return select_clusters_by_count(
            syns,
            soma_pds,
            pw_pds,
            n_clusters=self.n_clusters,
            n_per_cluster=self.n_per_cluster,
            soma_pd_mean=self.soma_pd_mean,
            soma_pd_sd=self.soma_pd_sd,
            raise_insufficient=False,
        )
