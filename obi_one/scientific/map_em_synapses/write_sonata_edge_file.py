import h5py
import numpy
from brainbuilder.utils.sonata.split_population import _write_indexes

_STR_PRE_NODE = "pre_node_id"
_STR_POST_NODE = "post_node_id"

def create_or_resize_dataset(grp, name, data, dtype=None):
    assert data.ndim == 1, "Datasets must be 1-dimensional!"
    l = len(data)

    if name in grp.keys():
        s = grp[name].shape
        assert len(s) == 1, "Datasets must be 1-dimensional!"
        s = s[0]
        grp[name].resize(s + l, axis=0)
        grp[name][s:] = data
    else:
        grp.create_dataset(name, data=data, maxshape=(None, ), dtype=dtype)

def adjust_edge_index_groups(grp_root, n_edges):
    create_or_resize_dataset(grp_root, "edge_type_id", -numpy.ones(n_edges, dtype=int), dtype="i8")
    create_or_resize_dataset(grp_root, "edge_group_id", numpy.zeros(n_edges, dtype=int), dtype="i8")
    start = 0
    if "edge_group_index" in grp_root.keys():
        if len(grp_root["edge_group_index"]) > 0:
            start = grp_root["edge_group_index"][-1] + 1
    edge_group_index = numpy.arange(start, start + n_edges, dtype=int)
    create_or_resize_dataset(grp_root, "edge_group_index", edge_group_index, dtype="u8")


def write_edges(fn_out, population_name, syn_pre_post, syn_data, source_pop_name, tgt_pop_name):
    h5 = h5py.File(fn_out, "a")

    grp_root = h5.require_group("edges/{0}".format(population_name))
    grp_0 = grp_root.require_group("0")

    create_or_resize_dataset(grp_root, "source_node_id", syn_pre_post[_STR_PRE_NODE].values)
    grp_root["source_node_id"].attrs["node_population"] = source_pop_name
    create_or_resize_dataset(grp_root, "target_node_id", syn_pre_post[_STR_POST_NODE].values)
    grp_root["target_node_id"].attrs["node_population"] = tgt_pop_name

    for _col in syn_data.columns:
        create_or_resize_dataset(grp_0, _col, syn_data[_col].values)
    adjust_edge_index_groups(grp_root, len(syn_pre_post))

    h5.close()
    n_src = len(syn_pre_post[_STR_PRE_NODE].drop_duplicates())
    n_tgt = len(syn_pre_post[_STR_POST_NODE].drop_duplicates())
    _write_indexes(fn_out, population_name, n_src, n_tgt)

