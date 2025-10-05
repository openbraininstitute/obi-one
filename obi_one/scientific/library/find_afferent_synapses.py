import warnings

import bluepysnap as snap
import morphio
import numpy  # noqa: ICN001
import pandas  # noqa: ICN001
from scipy import stats

try:
    from conntility.subcellular import MorphologyPathDistanceCalculator
except ImportError:
    warnings.warn("Connectome functionalities not available", UserWarning, stacklevel=1)


def morphology_and_pathdistance_calculator(
    circ: snap.Circuit, node_population: str, node_id: int
) -> tuple[morphio.Morphology, MorphologyPathDistanceCalculator]:
    """Loads for a specified neuron its morphology and creates a path-distance calculator object.

    Args:
      circ (bluepysnap.Circuit): The circuit the neuron resides in
      node_population (str): Name of the node population of the neuron
      node_id (int): Neuron node id.
    """
    node = circ.nodes[node_population]
    try:
        morph = node.morph.get(node_id, extension="h5")
    except Exception as err:
        msg = f"Error loading hdf5 morphology for {node_population} - {node_id}"
        raise RuntimeError(msg) from err
    PD = MorphologyPathDistanceCalculator(morph)  # noqa: N806
    return morph, PD


def all_syns_on(
    circ: snap.Circuit, node_population: str, node_id: int, node_props: list[str]
) -> pandas.DataFrame:
    """Load for a specified neuron relevant properties of all its afferent synapses across
    edge populations.

    Args:
      circ (bluepysnap.Circuit): The circuit the neuron resides in
      node_population (str): Name of the node population of the neuron
      node_id (int): Neuron node id.
      node_props (list): List of node properties. The values of these properties for
        the presynaptic partners of the afferent synapses will be loaded.
    """
    node = circ.nodes[node_population]
    syns = []
    syn_edge_names = []
    syn_pre_pop_names = []
    pre_node_props = []

    syn_props = [
        "afferent_section_id",
        "afferent_segment_id",
        "afferent_segment_offset",
        "@source_node",
        "@target_node",
    ]
    reserved_props = syn_props + ["source_population", "edge_population", "edge_id"]  # noqa: RUF005
    int_props = [
        "afferent_section_id",
        "afferent_segment_id",
        "@source_node",
        "@target_node",
        "edge_id",
    ]
    node_props_ = [_prop for _prop in node_props if _prop not in reserved_props]

    for edge_name in node.target_in_edges():
        edge = circ.edges[edge_name]
        if not numpy.all([_x in edge.property_names for _x in syn_props]):
            continue
        new_syns = edge.afferent_edges(node_id, properties=syn_props)
        if len(new_syns) == 0:
            continue
        syns.append(new_syns)
        pre_node = circ.nodes[edge.source.name]
        node_props__ = [_x for _x in node_props_ if _x in pre_node.property_names]
        loaded_node_props = pre_node.get(syns[-1]["@source_node"], properties=node_props__)
        loaded_node_props = loaded_node_props.reindex(
            columns=node_props_, index=syns[-1]["@source_node"].values
        )
        pre_node_props.append(loaded_node_props)
        syn_edge_names.append(edge_name)
        syn_pre_pop_names.append(edge.source.name)

    syns = pandas.concat(
        syns,
        axis=0,
        names=["source_population", "edge_population"],
        keys=list(zip(syn_pre_pop_names, syn_edge_names, strict=False)),
    )
    syns = syns.reset_index([2]).rename(columns={"level_2": "edge_id"})
    pre_node_props = pandas.concat(
        pre_node_props,
        axis=0,
        names=["source_population", "edge_population"],
        keys=list(zip(syn_pre_pop_names, syn_edge_names, strict=False)),
    )
    pre_node_props = pre_node_props.reset_index([2]).drop(columns=["node_ids"])

    syns = pandas.concat([syns, pre_node_props], axis=1).reset_index()

    for prop in int_props:
        syns[prop] = syns[prop].astype(int)

    return syns


# Section types are also in the synapse table, but I do not trust its presence in all circuits
def add_section_types(syns: pandas.DataFrame, morph: morphio.Morphology) -> None:
    """Load the section types of synaptic locations on a morphology.

    Args:
      syns (pandas.DataFrame): Dataframe that includes morphology locations in its columns, as
        they are specified in SONATA, e.g, "afferent_section_id".
      morph (morphio.Morphology): The morphology the locations are defined on
    """
    sec_types = numpy.array([1] + [int(_sec.type) for _sec in morph.sections])
    syns["afferent_section_type"] = sec_types[syns["afferent_section_id"]]


def apply_filters(
    syns: pandas.DataFrame, filter_dict: dict, *, drop_nan: bool = True
) -> pandas.DataFrame:
    """Filters a dataframe of synaptic locations according to specified property values.

    Args:
      syns (pandas.DataFrame): DataFrame with synapse properties. Can really be any types
        of properties as long as they are in different columns.
      filter_dict (dict): Specified filters. Keys of the dict specify the names of columns
        of the dataframe, values the values that pass the filter. A row has to pass ALL
        filters to be kept.
      drop_nan (bool, default: True): If set to False, then a nan value in a row is considered
        to pass the filter. Else, the row is dropped.
        Note however that nan values in columns that are not named in the keys of the
        filter_dict are ignored.
    """
    for k, v in filter_dict.items():
        if k not in syns.columns:
            msg = f"No property {k} could be loaded"
            raise ValueError(msg)  # This cannot happen! We check for it earlier.
        v_ = syns[k].isin(v) if isinstance(v, list) else syns[k] == v
        if not drop_nan:
            v_ = v_ | syns[k].isna()  # noqa: PLR6104
        syns = syns.loc[v_]
    return syns


def relevant_path_distances(
    PD: MorphologyPathDistanceCalculator,  # noqa: N803
    syns: pandas.DataFrame,
) -> tuple[numpy.ndarray, numpy.ndarray]:
    """Calculates and return path distances to the soma and all pairwise path distances for
    dendritic locations in a dataframe.

    Args:
      PD (conntility.subcellular.PathDistanceCalculator): Calculator for the relevant morphology.
      syns (pandas.DataFrame): Dataframe that includes morphology locations in its columns, as
        they are specified in SONATA, e.g, "afferent_section_id".
    """
    pw_pds = PD.path_distances(syns)

    soma = pandas.DataFrame(
        {"afferent_section_id": [0], "afferent_segment_id": [0], "afferent_segment_offset": [0.0]}
    )
    soma_pds = PD.path_distances(soma, locs_to=syns)[0]
    return soma_pds, pw_pds


def select_randomly(
    syns: pandas.DataFrame,
    n: int | None = None,
    p: float | None = None,
    *,
    raise_insufficient: bool = False,
) -> pandas.DataFrame:
    """From a set of synapse locations, given in a DataFrame, select some of them randomly.

    Args:
      syns (pandas.DataFrame): DataFrame with synapse properties. Can really be any types
        of properties as long as they are in different columns.
      n (int): Specify the number of synapses (i.e., rows of syns) to return.
      p (float): Specify that probability that each given synapse (i.e., row of syns) is
        selected and returned. If n is provided, this is ignored.
      raise_insufficient (bool, default=False): If set to True, then if n > len(syns) an
        exception is raised.
    """
    if n is not None:
        if raise_insufficient and (n > len(syns)):
            msg = f"Fewer than the requested count of {n} found!"
            raise RuntimeError(msg)
        return syns.iloc[numpy.random.choice(len(syns), numpy.minimum(n, len(syns)), replace=False)]  # noqa: NPY002
    if p is not None:
        if p < 0.0 or p > 1.0:
            msg = f"p: {p}, but must be between 0 and 1!"
            raise ValueError(msg)
        picked = numpy.random.rand(len(syns)) < p  # noqa: NPY002
        return syns.loc[picked]
    msg = "Must specify number or fraction of synapses!"
    raise ValueError(msg)


def select_minmax_distance(
    syns: pandas.DataFrame,
    soma_pds: numpy.ndarray,
    soma_pd_min: float,
    soma_pd_max: float,
    n: int | None = None,
    p: float | None = None,
    *,
    raise_insufficient: bool = False,
) -> pandas.DataFrame:
    """From a set of synapse locations, given in a DataFrame, select some of them randomly.
    But only select locations that are between a specified minimum and maximum path distance
    to the soma.

    Args:
      syns (pandas.DataFrame): DataFrame with synapse properties. Can really be any types
        of properties as long as they are in different columns.
      soma_pds (numpy.array): Specifies for each synapse its soma path distance.
      soma_pd_min (float): minimum soma path distance admitted.
      soma_pd_max (float): Maximum soma path distance admitted.
      n (int): Specify the number of synapses (i.e., rows of syns) to return.
      p (float): Specify that probability that each given synapse (i.e., row of syns) is
        selected and returned. If n is provided, this is ignored.
      raise_insufficient (bool, default=False): If set to True, then if n is larger than the
        number of synapses within the path distance interval, an exception is raised.
    """
    valid = (soma_pds >= soma_pd_min) & (soma_pds < soma_pd_max)
    return select_randomly(syns.loc[valid], n=n, p=p, raise_insufficient=raise_insufficient)


def select_closest_to_path_distance(
    syns: pandas.DataFrame,
    soma_pds: numpy.ndarray,
    target_soma_pd: float,
    n: int,
    *,
    raise_insufficient: bool = False,
) -> pandas.DataFrame:
    """From a set of synapse locations, given in a DataFrame, select the ones that are closest
    to a specified path distance from the soma.

    Args:
      syns (pandas.DataFrame): DataFrame with synapse properties. Can really be any types
        of properties as long as they are in different columns.
      soma_pds (numpy.array): Specifies for each synapse its soma path distance.
      target_soma_pd (float): Soma path distance that you want to get close to.
      n (int): Specify the number of synapses (i.e., rows of syns) to return. The
        n closest to the specified path distance will be picked. Note that they can
        be on very different branches.
      raise_insufficient (bool, default=False): If set to True, then if n is larger than
       len(syns) an exception is raised.
    """
    if raise_insufficient and (n > len(syns)):
        msg = f"Fewer than the requested count of {n} found!"
        raise RuntimeError(msg)
    srt_idx = numpy.argsort(numpy.abs(soma_pds - target_soma_pd))
    return syns.iloc[srt_idx[:n]]


def _pd_gaussian_selector(
    soma_pds: numpy.ndarray,
    soma_pd_mean: float,
    soma_pd_sd: float,
    n: int,
    *,
    raise_insufficient: bool = False,
) -> numpy.ndarray:
    """From a list of soma path distances, select some of them randomly with probabilities
    that depend on values of a path distance-dependent Gaussian.
    Returns the indices of elements that are picked from the list of path distances.

    Args:
      soma_pds (numpy.array): An array of path distance values.
      soma_pd_mean (float): Mean of a Gaussian that defines the probability function.
      soma_pd_sd (float): SD of the same Gaussian
      n (int): Specify the number of synapses (i.e., rows of syns) to return.
      raise_insufficient (bool, default=False): If set to True, then if n > len(syns) an
        exception is raised.
    """
    if (n > len(soma_pds)) and raise_insufficient:
        msg = f"Fewer than the requested count of {n} found!"
        raise RuntimeError(msg)

    distr = stats.norm(soma_pd_mean, soma_pd_sd).pdf(soma_pds)
    sel_idx = numpy.random.choice(  # noqa: NPY002
        range(len(soma_pds)), numpy.minimum(n, len(soma_pds)), p=distr / distr.sum()
    )
    return sel_idx


def select_by_path_distance(
    syns: pandas.DataFrame,
    soma_pds: numpy.ndarray,
    soma_pd_mean: float,
    soma_pd_sd: float,
    n: int | None = None,
    p: float | None = None,
    *,
    raise_insufficient: bool = False,
) -> pandas.DataFrame:
    """From a set of synapse locations, given in a DataFrame, select some of them randomly.
    The relative probabilities that each synapse is picked are defined by a parameterized
    Gaussian that depends on the path distances to the soma of the synapses.

    Args:
      syns (pandas.DataFrame): DataFrame with synapse properties. Can really be any types
        of properties as long as they are in different columns.
      soma_pds (numpy.array): An array of path distance values.
      soma_pd_mean (float): Mean of a Gaussian that defines the probability function.
      soma_pd_sd (float): SD of the same Gaussian
      n (int): Specify the number of synapses (i.e., rows of syns) to return.
      p (float): Specify that probability that each given synapse (i.e., row of syns) is
        selected and returned. If n is provided, this is ignored.
      raise_insufficient (bool, default=False): If set to True, then if n > len(syns) an
        exception is raised.
    """
    if p is not None:
        if p < 0.0 or p > 1.0:
            msg = f"p: {p}, but must be between 0 and 1!"
            raise ValueError(msg)
        n = stats.binom(len(syns), p).rvs()
    elif n is None:
        msg = "Must specify number or fraction of synapses!"
        raise ValueError(msg)
    return syns.iloc[
        _pd_gaussian_selector(
            soma_pds, soma_pd_mean, soma_pd_sd, n, raise_insufficient=raise_insufficient
        )
    ]


def select_clusters_by_max_distance(
    syns: pandas.DataFrame,
    soma_pds: numpy.ndarray,
    pw_pds: numpy.ndarray,
    n_clusters: int,
    cluster_max_distance: float,
    soma_pd_mean: float | None = None,
    soma_pd_sd: float | None = None,
    *,
    raise_insufficient: bool = False,
) -> pandas.DataFrame:
    """From a set of synapse locations, given in a DataFrame, select some of them randomly.
    The selected synapses will be clustered in the sense that their pairwise path distances
    are below a given value.
    Optionally, pick probabilities of all synapses depend on their soma path distance.

    Args:
      syns (pandas.DataFrame): DataFrame with synapse properties. Can really be any types
        of properties as long as they are in different columns.
      soma_pds (numpy.array): An array of path distance values for all synapses.
      pw_pds (numpy.array, len(syns) X len(syns)): Pairwise path distances between all pairs
      of locations in syns.
      n_clusters (int): Number of clusters to generate.
      cluster_max_distance (float): The maximum path distance of synapses within a cluster
      from the center of that cluster. All synapses within that distance will be picked.
      soma_pd_mean (float, optional): Mean of a Gaussian that defines a path distance-dependent
        probability function that biases the synapse selection. If it is not specified, then
        synapses at all path distances are equally likely to be picked.
      soma_pd_sd (float, optional): SD of the same Gaussian.
      raise_insufficient (bool, default=False): If set to True, then if the specified number
      of clusters cannot be generated, an exception is raised.
    """
    syns_out = []
    for _ in range(n_clusters):
        if raise_insufficient and (len(syns) == 0):
            if raise_insufficient:
                msg = f"Fewer than the requested count of {n_clusters} clusters possible!"
                raise RuntimeError(msg)
            break
        if soma_pd_mean is not None and soma_pd_sd is not None:
            ctr = _pd_gaussian_selector(
                soma_pds, soma_pd_mean, soma_pd_sd, 1, raise_insufficient=True
            )[0]
        else:
            ctr = numpy.random.choice(len(syns))  # noqa: NPY002
        clstr_ids = pw_pds[ctr] < cluster_max_distance
        syns_out.append(syns.loc[clstr_ids])
        syns = syns.loc[~clstr_ids]
        pw_pds = pw_pds[numpy.ix_(~clstr_ids, ~clstr_ids)]
        if soma_pds is not None:
            soma_pds = soma_pds[~clstr_ids]
    return pandas.concat(
        syns_out, axis=0, names=["cluster_id"], keys=range(len(syns_out))
    ).reset_index(0)


def select_clusters_by_count(
    syns: pandas.DataFrame,
    soma_pds: numpy.ndarray,
    pw_pds: numpy.ndarray,
    n_clusters: int,
    n_per_cluster: int,
    soma_pd_mean: float | None = None,
    soma_pd_sd: float | None = None,
    *,
    raise_insufficient: bool = False,
) -> pandas.DataFrame:
    """From a set of synapse locations, given in a DataFrame, select some of them randomly.
    The selected synapses will be clustered in the sense that synapses are selected
    together with all their nearest neighbors in terms of path distance.
    Optionally, pick probabilities of all synapses depend on their soma path distance.

    Args:
      syns (pandas.DataFrame): DataFrame with synapse properties. Can really be any types
        of properties as long as they are in different columns.
      soma_pds (numpy.array): An array of path distance values for all synapses.
      pw_pds (numpy.array, len(syns) X len(syns)): Pairwise path distances between all pairs
      of locations in syns.
      n_clusters (int): Number of clusters to generate.
      n_per_cluster (int): After picking a synapse as the center of a cluster, its
      n_per_cluster - 1 nearest neighbors are also included. However, synapses that have been
      picked for one cluster cannot be picked again for another cluster, even if sufficiently
      near.
      soma_pd_mean (float, optional): Mean of a Gaussian that defines a path distance-dependent
        probability function that biases the synapse selection. If it is not specified, then
        synapses at all path distances are equally likely to be picked.
      soma_pd_sd (float, optional): SD of the same Gaussian.
      raise_insufficient (bool, default=False): If set to True, then if the specified number
      of clusters cannot be generated, an exception is raised.
    """
    syns_out = []
    for _ in range(n_clusters):
        if len(syns) < n_per_cluster:
            if raise_insufficient:
                msg = f"Fewer than the requested count of {n_clusters} clusters possible!"
                raise RuntimeError(msg)
            break
        if soma_pd_mean is not None and soma_pd_sd is not None:
            ctr = _pd_gaussian_selector(
                soma_pds, soma_pd_mean, soma_pd_sd, 1, raise_insufficient=True
            )[0]
        else:
            ctr = numpy.random.choice(len(syns))  # noqa: NPY002
        clstr_ids = numpy.argsort(pw_pds[ctr])[:n_per_cluster]
        other_ids = numpy.setdiff1d(range(len(syns)), clstr_ids)
        syns_out.append(syns.iloc[clstr_ids])
        syns = syns.iloc[other_ids]
        pw_pds = pw_pds[numpy.ix_(other_ids, other_ids)]
        if soma_pds is not None:
            soma_pds = soma_pds[other_ids]
    return pandas.concat(
        syns_out, axis=0, names=["cluster_id"], keys=range(len(syns_out))
    ).reset_index(0)


def merge_multiple_syns_per_connection(
    syns: pandas.DataFrame, soma_pds: numpy.ndarray, pw_pds: numpy.ndarray
) -> tuple[pandas.DataFrame, numpy.ndarray, numpy.ndarray]:
    syns = syns.reset_index(drop=True)
    grp_ = (
        syns.reset_index(drop=False)
        .groupby(["source_population", "@source_node"])["index"]
        .apply(list)
    )
    mn_soma_pd = grp_.apply(lambda _x: soma_pds[_x].mean())
    mn_pw_pds = grp_.apply(lambda _x: grp_.apply(lambda _y: pw_pds[numpy.ix_(_x, _y)].mean()))

    syns_out = mn_soma_pd.index.to_frame().reset_index(drop=True)
    mn_soma_pd = mn_soma_pd.to_numpy()
    mn_pw_pds = mn_pw_pds.to_numpy()
    return syns_out, mn_soma_pd, mn_pw_pds
