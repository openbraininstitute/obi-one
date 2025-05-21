import pandas
import numpy
import neurom
import os.path

from voxcell import CellCollection
from scipy.spatial import transform

_C_NRN_LOCS = ["x", "y", "z"]
_STR_ORIENT = "orientation"
_STR_NONE = "_NONE"
_STR_MORPH = "morphology"
_PREF_SRC = "source__"

__unit_rot = numpy.array([
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1]
]).astype(float)

def estimate_vertical(nrns):
    def estimate_layer(ct_in):
        try:
            return int(ct_in[0])
        except:
            return numpy.nan
        
    l = nrns["cell_type"].apply(estimate_layer)
    l.name = "layer"
    mn_layer_pos = pandas.concat([nrns[_C_NRN_LOCS], l], axis=1).groupby("layer")[_C_NRN_LOCS].mean().sort_index(ascending=False)
    mn_delta_vec = mn_layer_pos.diff(axis=0).mean()
    vertical = mn_delta_vec.values / numpy.linalg.norm(mn_delta_vec.values)
    return vertical 

def estimate_volume_rotation(nrns):
    v = estimate_vertical(nrns)
    neutral = numpy.array([0, 1, 0])
    rot = transform.Rotation.align_vectors(v, neutral)[0] # transform [0, 1, 0] into "vertical"
    return rot


def source_resolution(client):
    resolutions = numpy.array(
        [client.info.get_datastack_info()["viewer_resolution_{0}".format(_coord)]
        for _coord in ["x", "y", "z"]]
    )
    return resolutions

def neuron_info_df(client, table_name, filters, add_position=True):
    q_cells = client.materialize.query_table(table_name)

    for k, v in filters.items():
        q_cells = q_cells.loc[q_cells[k] == v]

    vc = q_cells["pt_root_id"].value_counts()
    q_cells = q_cells.set_index("pt_root_id").loc[vc[vc == 1].index]

    if add_position:
        resolutions = source_resolution(client)
        nrn_locs = q_cells["pt_position"].apply(lambda _x: pandas.Series(_x * resolutions / 1000.0,
                                                                        index=_C_NRN_LOCS))
        q_cells = pandas.concat([q_cells, nrn_locs], axis=1)

    return q_cells


def translate(node_series, morph):
    node_loc = node_series[["x", "y", "z"]].values.reshape((1, -1))
    tl_morph = morph.transform(lambda _x: _x + node_loc)
    return tl_morph


def rotate(node_series, morph):
    _col = "orientation"
    rot = transform.Rotation.from_matrix(node_series[_col])
    return morph.transform(rot.apply)


def untranslate(node_series, morph):
    assert numpy.linalg.norm(morph.soma.center - node_series[_C_NRN_LOCS]) < 10.0
    node_loc = node_series[_C_NRN_LOCS].values.reshape((1, -1))
    tl_morph = morph.transform(lambda _x: _x - node_loc)
    return tl_morph


def unrotate(node_series, morph):
    rot = transform.Rotation.from_matrix(node_series[_STR_ORIENT])
    tl_morph = morph.transform(lambda _x: rot.apply(_x, inverse=True))
    return tl_morph


def transform_and_copy_morphologies(nrns, in_root, out_root, out_formats=(".h5", ".swc")):
    if not os.path.isdir(out_root):
        os.makedirs(out_root)
    morph_name_pat = "{0}.swc"
    spines_name_pat = "{0}-spines.json"

    for _idx in nrns.index:
        morph_fn = morph_name_pat.format(_idx)
        if not (os.path.isfile(os.path.join(in_root, morph_fn)) and
                os.path.isfile(os.path.join(in_root, spines_name_pat.format(_idx)))):
            nrns.loc[_idx, _STR_MORPH] = _STR_NONE
            continue

        morph_fn = morph_name_pat.format(_idx)
        morph = neurom.io.utils.load_morphology(os.path.join(in_root, morph_fn),
                                                mutable=True)
        new_morph = untranslate(nrns.loc[_idx], morph)
        new_morph = unrotate(nrns.loc[_idx], new_morph)
        new_morph.name = str(_idx)
        nrns.loc[_idx, _STR_MORPH] = new_morph.name
        for ext in out_formats:
            new_morph.to_morphio().write(os.path.join(out_root, new_morph.name + ext))


def neuron_info_to_collection(nrn, name, cols_to_rename, cols_to_keep):
    rename_dict = {}
    for _col in cols_to_rename:
        rename_dict[_col] = _PREF_SRC + _col

    nrn_out = pandas.concat([nrn[list(rename_dict.keys())].rename(columns=rename_dict),
                nrn[cols_to_keep]
    ], axis=1)
    nrn_out["pt_root_id"] = nrn_out.index
    # nrn_out["morphology"] = nrn_out["pt_root_id"].astype(str)
    nrn_out.index = pandas.RangeIndex(1, len(nrn_out) + 1)

    coll = CellCollection.from_dataframe(nrn_out)
    coll.population_name = name

    return coll

def collection_to_neuron_info(path_to_file, must_exist=True):
    if os.path.isfile(path_to_file):
        coll = CellCollection.load_sonata(path_to_file)
        df = coll.as_dataframe()
        df.index = df.index - 1
        return df, coll.population_name
    elif must_exist:
        raise ValueError("{0} is not a valid file!".format(path_to_file))
    
    empty_df = pandas.DataFrame({
        "x": numpy.empty((0,), dtype=float),
        "y": numpy.empty((0,), dtype=float),
        "z": numpy.empty((0,), dtype=float),
        "pt_root_id": numpy.empty((0,), dtype=int)
    })
    return empty_df, "microns_extrinsic"
