import h5py
import numpy

from .utils_edges import (
    _STR_PRE_NODE,
    _STR_POST_NODE
)

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


def remove_postsynaptic_ids_from_edges(idx_to_purge, fn_edges_in, fn_edges_out, node_pop_sizes_dict):
    import h5py
    from brainbuilder.utils.sonata.split_population import _write_indexes

    h5 = h5py.File(fn_edges_in, "r")
    grp_root_in = h5["edges"]
    edge_pop_names = list(grp_root_in.keys())
    source_target_pop_sizes = {}
    for edge_pop in edge_pop_names:
        grp_in = grp_root_in[edge_pop]
        ranges_to_delete = grp_in["indices/target_to_source/node_id_to_ranges"][idx_to_purge]
        edge_ids_to_delete = numpy.vstack([grp_in["indices/target_to_source/range_to_edge_id"][a:b]
                                   for a, b in ranges_to_delete])
        edge_ids_to_delete = edge_ids_to_delete[numpy.argsort(edge_ids_to_delete[:, 0])]
        assert (numpy.diff(edge_ids_to_delete[:, 0]) >= 0).all()
        assert (numpy.diff(edge_ids_to_delete[:, 1]) >= 0).all()
        l = grp_in["target_node_id"].shape[0]

        edge_ids_to_keep = numpy.vstack(
            [
                [0] + edge_ids_to_delete[:, 1].tolist(),
                edge_ids_to_delete[:, 0].tolist() + [l]
            ]
        ).transpose()
        n_edges = numpy.diff(edge_ids_to_keep, axis=1).sum()
        
        with h5py.File(fn_edges_out, "w") as h5_out:
            grp = h5_out.create_group("edges")
            grp = grp.create_group(edge_pop)
            grp0 = grp.create_group("0")

            for k in grp_in["0"].keys():
                data = numpy.hstack([grp_in["0"][k][a:b]
                        for a, b in edge_ids_to_keep])
                grp0.create_dataset(k, data=data, maxshape=(None, ))

            for k in ["source_node_id", "target_node_id"]:
                data = numpy.hstack([grp_in[k][a:b]
                            for a, b in edge_ids_to_keep])
                dset = grp.create_dataset(k,
                                          data=data,
                                          maxshape=(None, ))
                _node_pop = grp_in[k].attrs["node_population"]
                dset.attrs["node_population"] = _node_pop
                source_target_pop_sizes.setdefault(edge_pop, {})[k] = node_pop_sizes_dict[_node_pop]
                
            adjust_edge_index_groups(grp, n_edges)
            h5_out.flush()
    h5.close()
    for edge_pop in edge_pop_names:
        _write_indexes(fn_edges_out,
                       edge_pop,
                       source_target_pop_sizes[edge_pop]["source_node_id"],
                       source_target_pop_sizes[edge_pop]["target_node_id"]
                       )
