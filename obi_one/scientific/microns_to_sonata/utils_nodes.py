import pandas
import numpy
import neurom
import shutil
import h5py
import os.path

from voxcell import CellCollection
from scipy.spatial import transform

_C_NRN_LOCS = ["x", "y", "z"]
_STR_ORIENT = "orientation"
_STR_NONE = "_NONE"
_STR_MORPH = "morphology"
_STR_SPINE_INFO = "spine_info"
_PREF_SRC = "source__"

__unit_rot = numpy.array([
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1]
]).astype(float)

def estimate_vertical(nrns):
    def estimate_layer(ct_in, _idx=0):
        try:
            return int(ct_in[_idx])
        except:
            return numpy.nan
        
    if "layer" in nrns.columns:
        l = nrns["layer"].apply(estimate_layer, _idx=-1)
        # l = nrns["layer"]
    else:
        l = nrns["cell_type"].apply(estimate_layer, _idx=1)
    print(l.value_counts())
    l.name = "layer"
    mn_layer_pos = pandas.concat([nrns[_C_NRN_LOCS], l], axis=1).groupby("layer")[_C_NRN_LOCS].mean().sort_index(ascending=False)
    mn_layer_pos = mn_layer_pos.loc[mn_layer_pos.index > 0]
    mn_delta_vec = mn_layer_pos.diff(axis=0).mean()
    vertical = mn_delta_vec.values / numpy.linalg.norm(mn_delta_vec.values)
    return vertical

def estimate_volume_rotation(nrns, volume_vertical=None):
    if volume_vertical is None:
        v = estimate_vertical(nrns)
    else:
        v = numpy.array(list(volume_vertical))
    neutral = numpy.array([0, 1, 0])
    rot = transform.Rotation.align_vectors(v, neutral)[0] # transform [0, 1, 0] into "vertical"
    return rot

def apply_filters(df, filters):
    for k, v in filters.items():
        if isinstance(v, tuple) or isinstance(v, list):
            df = df.loc[df[k].isin(v)]
        else:
            df = df.loc[df[k] == v]
    return df

def source_resolution(client):
    resolutions = numpy.array(
        [client.info.get_datastack_info()["viewer_resolution_{0}".format(_coord)]
        for _coord in ["x", "y", "z"]]
    )
    return resolutions

def get_node_pop_name(fn):
    with h5py.File(fn, "r") as h5:
        node_pop_name = list(h5["nodes"].keys())[0]
    return node_pop_name

def get_node_pop_count(fn):
    pop_name = get_node_pop_name(fn)
    with h5py.File(fn, "r") as h5:
        n = h5["nodes"][pop_name]["node_type_id"].shape[0]
    return n

def neuron_info_df(client, table_name, filters, add_position=True):
    q_cells = client.materialize.query_table(table_name)

    q_cells = apply_filters(q_cells, filters)

    vc = q_cells["pt_root_id"].value_counts()
    q_cells = q_cells.set_index("pt_root_id").loc[vc[vc == 1].index]

    if add_position:
        resolutions = source_resolution(client)
        nrn_locs = q_cells["pt_position"].apply(lambda _x: pandas.Series(_x * resolutions / 1000.0,
                                                                        index=_C_NRN_LOCS))
        q_cells = pandas.concat([q_cells, nrn_locs], axis=1)

    return q_cells

def neuron_info_from_somas_file(client, fn_somas_file, reference_df):
    # I have independently validated that this method of matching neurons by
    # locations provides meaningful results. --MWR
    from scipy.spatial import KDTree
    somas = pandas.read_csv(fn_somas_file)
    # Hard coded filter. Sorry.
    somas.loc[somas["c3_rep_strict"].dropna().index]
    somas["proofread_104_rep"] = somas["proofread_104_rep"].fillna(0)
    somas["proofread_104_rep"] = somas["proofread_104_rep"].astype(int)

    res = source_resolution(client)
    for _res, _col in zip(res, _C_NRN_LOCS):
        somas[_col] = _res * somas[_col] / 1000.0
    
    t_soma_file = KDTree(somas[_C_NRN_LOCS])
    t_reference = KDTree(reference_df[_C_NRN_LOCS])
    matched = t_soma_file.query_ball_tree(t_reference, 1E-6) # For each entry in "somas" its matches
    assert numpy.all([len(_x) <= 1 for _x in matched]) # No more than a single match
    print("{0} percent of neurons were matched".format(
        100 * numpy.mean([len(_x) > 0 for _x in matched])))
    somas["pt_root_id"] = numpy.hstack([reference_df.index[_x[0]]
                                        if len(_x) > 0 else -1 for _x in matched])
    somas = somas.loc[somas["pt_root_id"] > 0]
    somas = somas.loc[somas["pt_root_id"].isin(reference_df.index)]
    return somas.set_index("pt_root_id").drop(columns=["x", "y", "z"])

def post_process_neuron_info(df, lst_pp_funcs):
    obj_out = []
    cols_drop = []
    for _col, _func in lst_pp_funcs:
        obj_out.append(_func(df[_col]))
        if _col not in cols_drop: cols_drop.append(_col)
    return pandas.concat(
        [df.drop(columns=cols_drop)] + obj_out,
        axis=1
    )

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


def transform_and_copy_morphologies(nrns, in_root, out_root,
                                    naming_patters=("{pt_root_id}.swc", "{pt_root_id}-spines.json"),
                                    out_formats=("h5", "swc"),
                                    do_transform=True):
    for out_format in out_formats:
        if not os.path.isdir(os.path.join(out_root, out_format)):
            os.makedirs(os.path.join(out_root, out_format))
    spine_out_root = out_root
    if len(out_formats) > 0:
        spine_out_root = os.path.join(out_root, out_formats[0])
    morph_name_pat, spines_name_pat = naming_patters

    for _, _row in nrns.reset_index().iterrows():
        _idx = _row["pt_root_id"]
        morph_fn = morph_name_pat.format(**_row.to_dict())
        spines_fn = spines_name_pat.format(**_row.to_dict())
        nrns.loc[_idx, _STR_MORPH] = _STR_NONE
        nrns.loc[_idx, _STR_SPINE_INFO] = _STR_NONE
        if not os.path.isfile(os.path.join(in_root, morph_fn)):
            continue
        try:
            morph = neurom.io.utils.load_morphology(os.path.join(in_root, morph_fn),
                                                    mutable=True)
            if do_transform:
                morph = untranslate(nrns.loc[_idx], morph)
                morph = unrotate(nrns.loc[_idx], morph)
            else:
                nrns.loc[_idx, _C_NRN_LOCS] = 0.0
                nrns.loc[[_idx], _STR_ORIENT] = [__unit_rot]
            morph.name = str(_idx)
            
            for ext in out_formats:
                morph.to_morphio().write(os.path.join(out_root, ext, morph.name + "." + ext))
            nrns.loc[_idx, _STR_MORPH] = morph.name
            print(f"Morphology {morph_fn} found and moved!")
            if os.path.isfile(os.path.join(in_root, spines_fn)):
                spines_name = "spines_" + morph.name
                shutil.copy(os.path.join(in_root, spines_fn),
                            os.path.join(spine_out_root, spines_name + ".json"))
                nrns.loc[_idx, _STR_SPINE_INFO] = spines_name
        except Exception as e:
            print(f"Morphology {morph_fn} found but an error was encountered!")
            print(str(e))
            pass
    n_found = (nrns[_STR_MORPH] != _STR_NONE).sum()
    print(f"{n_found} morphologies found and moved!")

def split_into_intrinsic_and_virtual(nrn, use_bounding_box=True, expand_bounding_box=0.0):
    has_morphology = nrn[_STR_MORPH] != _STR_NONE
    if not use_bounding_box:
        return nrn.loc[has_morphology], nrn.loc[~has_morphology]
    if numpy.isinf(expand_bounding_box):
        return nrn, nrn.iloc[:0]
    nrn_morph = nrn.loc[has_morphology]
    if (len(nrn_morph) == 0):
        print("No morphologies assigned. Using center!")
        bb_mean = nrn[_C_NRN_LOCS].mean()
        sz = pandas.Series({_col: expand_bounding_box for _col in _C_NRN_LOCS})
        bb_min = bb_mean - sz; bb_max = bb_mean + sz
    else:
        bb_min = nrn_morph[_C_NRN_LOCS].min()
        bb_max = nrn_morph[_C_NRN_LOCS].max()
        bb_min = bb_min - expand_bounding_box * (bb_max - bb_min)
        bb_max = bb_max + expand_bounding_box * (bb_max - bb_min)

    in_bb = ((nrn[["x", "y", "z"]] >= bb_min) & (nrn[["x", "y", "z"]] <= bb_max)).all(axis=1)
    return nrn.loc[in_bb], nrn.loc[~in_bb]

def neuron_info_to_collection(nrn, name, cols_to_rename, cols_to_keep, specific_renames="none"):
    rename_dict = {}
    for _col in cols_to_rename:
        rename_dict[_col] = _PREF_SRC + _col

    nrn_out = pandas.concat([nrn[list(rename_dict.keys())].rename(columns=rename_dict),
                nrn[cols_to_keep]
    ], axis=1).dropna()
    nrn_out["pt_root_id"] = nrn_out.index
    nrn_out = post_process_neuron_info(nrn_out, get_node_prop_post_processors(specific_renames))
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
    return empty_df, "em_extrinsic"

def get_node_prop_post_processors(str_type):
    if str_type == "h01":
        def parse_layer(str_in):
            if isinstance(str_in, float): return "N/A"
            if str_in.startswith("Layer"):
                return str(int(str_in[5:]))
            if str_in.startswith("White"):
                return "white_matter"
            return "N/A"

        def pp_layer(series_in):
            series_out = series_in.apply(parse_layer)
            series_out.name = "layer"
            return series_out

        lst_exc = ["PYRAMIDAL", "SPINY_STELLATE", "SPINY_ATYPICAL"]
        lst_inh = ["INTERNEURON"]
        def parse_syn_class(str_in):
            if str_in in lst_exc: return "EXC"
            if str_in in lst_inh: return "INH"
            return "N/A"

        def pp_syn_class(series_in):
            series_out = series_in.apply(parse_syn_class)
            series_out.name = "synapse_class"
            return series_out

        def pp_mtype(series_in):
            series_out = series_in.copy()
            series_out.name = "mtype"
            return series_out

        pp_lst = [
            (_PREF_SRC + "layer", pp_layer),
            (_PREF_SRC + "celltype", pp_syn_class),
            (_PREF_SRC + "celltype", pp_mtype)
        ]
        return pp_lst
    if str_type == "microns":
        def pp_syn_class(series_in):
            series_out = series_in.apply(lambda _x: _x[:3].upper())
            series_out.name = "synapse_class"
            return series_out
        
        def pp_mtype(series_in):
            series_out = series_in.copy()
            series_out.name = "mtype"
            return series_out
        
        def parse_layer(str_in):
            try:
                layer_int = int(str_in[1])
                return str(layer_int)
            except:
                return "N/A"

        def pp_layer(series_in):
            series_out = series_in.apply(parse_layer)
            series_out.name = "layer"
            return series_out
        
        pp_lst = [
            (_PREF_SRC + "cell_type", pp_layer),
            (_PREF_SRC + "classification_system", pp_syn_class),
            (_PREF_SRC + "cell_type", pp_mtype)
        ]
        return pp_lst
        
    if str_type == "none":
        return []
    raise ValueError("Unknown value: {0}".format(str_type))
