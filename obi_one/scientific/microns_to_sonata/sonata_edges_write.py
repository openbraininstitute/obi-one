import h5py

from .utils_edges import (
    _STR_PRE_NODE,
    _STR_POST_NODE
)

def create_or_resize_dataset(grp, name, data):
    assert data.ndim == 1, "Datasets must be 1-dimensional!"
    l = len(data)

    if name in grp.keys():
        s = grp[name].shape
        assert len(s) == 1, "Datasets must be 1-dimensional!"
        s = s[0]
        grp[name].resize(s + l, axis=0)
        grp[name][s:] = data
    else:
        grp.create_dataset(name, data=data, maxshape=(None, ))


def write_edges(fn_out, population_name, syn_pre_post, syn_data):
    h5 = h5py.File(fn_out, "a")

    grp_root = h5.require_group("edges/{0}".format(population_name))
    grp_0 = grp_root.require_group("0")

    create_or_resize_dataset(grp_root, "source_node_id", syn_pre_post[_STR_PRE_NODE].values)
    create_or_resize_dataset(grp_root, "target_node_id", syn_pre_post[_STR_POST_NODE].values)

    for _col in syn_data.columns:
        create_or_resize_dataset(grp_0, _col, syn_data[_col].values)

    h5.close()
