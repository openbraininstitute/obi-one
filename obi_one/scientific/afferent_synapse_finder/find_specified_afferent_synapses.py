import numpy
import pandas
import os
import morphio

from scipy import stats
from conntility.subcellular import MorphologyPathDistanceCalculator

def morphology_and_pathdistance_calculator(circ, node_population, node_id):
    node = circ.nodes[node_population]
    morph_name = node.morph.get_name(node_id)
    try:
        morph = morphio.Morphology(os.path.join(node.config["alternate_morphologies"]["h5v1"], morph_name) + ".h5")
    except:
        raise RuntimeError("Error loading hdf5 morphology for {0} - {1}".format(node_population, node_id))
    PD = MorphologyPathDistanceCalculator(morph)
    return morph, PD


def all_syns_on(circ, node_population, node_id, node_props):
    node = circ.nodes[node_population]
    syns = []
    syn_edge_names = []
    syn_pre_pop_names = []
    pre_node_props = []

    syn_props = ["afferent_section_id", "afferent_segment_id",
                 "afferent_segment_offset",
                 "@source_node", "@target_node"]
    reserved_props = syn_props + ["source_population", "edge_population", "edge_id"]
    int_props = ["afferent_section_id", "afferent_segment_id", "@source_node", "@target_node", "edge_id"]
    _node_props = [_prop for _prop in node_props if _prop not in reserved_props]
    
    for edge_name in node.target_in_edges():
        edge = circ.edges[edge_name]
        if not numpy.all([_x in edge.property_names for _x in syn_props]):
            print("Skipping!")
            continue
        new_syns = edge.afferent_edges(node_id, properties=syn_props)
        if len(new_syns) == 0:
            continue
        syns.append(new_syns)
        pre_node = circ.nodes[edge.source.name]
        __node_props = [_x for _x in _node_props if _x in pre_node.property_names]
        loaded_node_props = pre_node.get(syns[-1]["@source_node"], properties=__node_props)
        loaded_node_props = loaded_node_props.reindex(columns=_node_props, index=syns[-1]["@source_node"].values)
        pre_node_props.append(loaded_node_props)
        syn_edge_names.append(edge_name)
        syn_pre_pop_names.append(edge.source.name)

    syns = pandas.concat(syns, axis=0, names=["source_population", "edge_population"],
                         keys=list(zip(syn_pre_pop_names, syn_edge_names)))
    syns = syns.reset_index([2]).rename(columns={"level_2": "edge_id"})
    pre_node_props = pandas.concat(pre_node_props, axis=0, names=["source_population", "edge_population"],
                                   keys=list(zip(syn_pre_pop_names, syn_edge_names)))
    pre_node_props = pre_node_props.reset_index([2]).drop(columns=["node_ids"])

    syns = pandas.concat([syns, pre_node_props], axis=1).reset_index()

    for prop in int_props:
        syns[prop] = syns[prop].astype(int)

    return syns

# Section types are also in the synapse table, but I do not trust its presence in all circuits
def add_section_types(syns, morph):
    sec_types = numpy.array([1] + [int(_sec.type) for _sec in morph.sections])
    syns["afferent_section_type"] = sec_types[syns["afferent_section_id"]]


def apply_filters(syns, filter_dict, drop_nan=True):
    for k, v in filter_dict.items():
        assert k in syns.columns, "No property {0} could be loaded".format(k)  # This cannot happen!
        if isinstance(v, list):
            v = syns[k].isin(v)
        else:
            v = syns[k] == v
        if not drop_nan:
            v = v | syns[k].isna()
        syns = syns.loc[v]
    return syns

def relevant_path_distances(PD, syns):
    pw_pds = PD.path_distances(syns)

    soma = pandas.DataFrame({"afferent_section_id": [0], "afferent_segment_id": [0], "afferent_segment_offset": [0.0]})
    soma_pds = PD.path_distances(soma, locs_to=syns)[0]
    return soma_pds, pw_pds


def select_randomly(syns, n=None, p=None, raise_insufficient=False):
    assert p is not None or n is not None, "Must specify number or fraction of synapses!"
    if n is not None:
        if n > len(syns):
            if raise_insufficient:
                raise RuntimeError("Fewer than the requested count of {0} found!".format(n))
        return syns.iloc[numpy.random.choice(len(syns), numpy.minimum(n, len(syns)), replace=False)]
    if p is not None:
        if p < 0.0 or p > 1.0:
            raise ValueError("p must be between 0 and 1!")
        picked = numpy.random.rand(len(syns)) < p
        return syns.loc[picked]

def select_minmax_distance(syns, soma_pds, soma_pd_min, soma_pd_max, n=None, p=None, raise_insufficient=False):
    valid = (soma_pds >= soma_pd_min) & (soma_pds < soma_pd_max)
    return select_randomly(syns.loc[valid], n=n, p=p, raise_insufficient=raise_insufficient)

def select_closest_to_path_distance(syns, soma_pds, target_soma_pd, n, raise_insufficient=False):
    if n > len(syns):
        if raise_insufficient:
            raise RuntimeError("Fewer than the requested count of {0} found!".format(n))
    srt_idx = numpy.argsort(numpy.abs(soma_pds - target_soma_pd))
    return syns.iloc[srt_idx[:n]]

def _pd_gaussian_selector(soma_pds, soma_pd_mean, soma_pd_sd, n, raise_insufficient=False):
    if (n > len(soma_pds)) and raise_insufficient:
        raise RuntimeError("Fewer than the requested count of {0} found!".format(n))
    
    distr = stats.norm(soma_pd_mean, soma_pd_sd).pdf(soma_pds)
    sel_idx = numpy.random.choice(range(len(soma_pds)), numpy.minimum(n, len(soma_pds)),
                                  p=distr/distr.sum())
    return sel_idx

def select_by_path_distance(syns, soma_pds, soma_pd_mean, soma_pd_sd, n=None, p=None, raise_insufficient=False):
    assert p is not None or n is not None, "Must specify number or fraction of synapses!"
    if p is not None:
        if p < 0.0 or p > 1.0:
            raise ValueError("p must be between 0 and 1!")
        n = stats.binom(len(syns), p).rvs()
    return syns.iloc[_pd_gaussian_selector(soma_pds, soma_pd_mean, soma_pd_sd,
                                            n, raise_insufficient=raise_insufficient)]

def select_clusters_by_max_distance(syns, soma_pds, pw_pds, n_clusters, cluster_max_distance, 
                                    soma_pd_mean=None, soma_pd_sd=None,
                                    raise_insufficient=False):
    syns_out = []
    for _ in range(n_clusters):
        if len(syns) == 0:
            if raise_insufficient:
                raise RuntimeError("Fewer than the requested count of {0} clusters possible!".format(n_clusters))
            break
        if soma_pd_mean is not None and soma_pd_sd is not None:
            ctr = _pd_gaussian_selector(soma_pds, soma_pd_mean, soma_pd_sd, 1,
                                        raise_insufficient=True)[0]
        else:
            ctr = numpy.random.choice(len(syns))
        clstr_ids = pw_pds[ctr] < cluster_max_distance
        syns_out.append(syns.loc[clstr_ids])
        syns = syns.loc[~clstr_ids]
        pw_pds = pw_pds[numpy.ix_(~clstr_ids, ~clstr_ids)]
        if soma_pds is not None:
            soma_pds = soma_pds[~clstr_ids]
    return pandas.concat(syns_out, axis=0, names=["cluster_id"], keys=range(len(syns_out))).reset_index(0)

def select_clusters_by_count(syns, soma_pds, pw_pds, n_clusters, n_per_cluster,
                             soma_pd_mean=None, soma_pd_sd=None,
                             raise_insufficient=False):
    syns_out = []
    for _ in range(n_clusters):
        if len(syns) < n_per_cluster:
            if raise_insufficient:
                raise RuntimeError("Fewer than the requested count of {0} clusters possible!".format(n_clusters))
            break
        if soma_pd_mean is not None and soma_pd_sd is not None:
            ctr = _pd_gaussian_selector(soma_pds, soma_pd_mean, soma_pd_sd, 1,
                                        raise_insufficient=True)[0]
        else:
            ctr = numpy.random.choice(len(syns))
        clstr_ids = numpy.argsort(pw_pds[ctr])[:n_per_cluster]
        other_ids = numpy.setdiff1d(range(len(syns)), clstr_ids)
        syns_out.append(syns.iloc[clstr_ids])
        syns = syns.iloc[other_ids]
        pw_pds = pw_pds[numpy.ix_(other_ids, other_ids)]
        if soma_pds is not None:
            soma_pds = soma_pds[other_ids]
    return pandas.concat(syns_out, axis=0, names=["cluster_id"], keys=range(len(syns_out))).reset_index(0)
