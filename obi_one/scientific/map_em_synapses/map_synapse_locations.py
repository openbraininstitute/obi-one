import numpy
import pandas
import tqdm

from scipy.spatial.transform import Rotation
from scipy.spatial import KDTree

# Columns of edge table dataframes
_C_P_LOCS = ["synapse_x", "synapse_y", "synapse_z"]
_C_SEG_S = ["start_x", "start_y", "start_z"]
_C_SEG_S_F = _C_SEG_S + ["start_d"]
_C_SEG_E = ["end_x", "end_y", "end_z"]
_C_SEG_E_F = _C_SEG_E + ["end_d"]
_C_SPINE_MESH = "spine_morphology"
_C_SPINE_ID = "spine_id"
_C_SP_INDEX = "spine_sharing_id"
_C_SHARING_ID = "spine_sharing_id"
_C_PSD_ID = "spine_psd_id"
_C_ROTATION = ["spine_rotation_x", "spine_rotation_y",	"spine_rotation_z",	"spine_rotation_w"]
_C_TRANSLATION = ["afferent_surface_x", "afferent_surface_y", "afferent_surface_z"]
_C_CENTER = ["center_x", "center_y", "center_z"]
_C_SURFACE = ["surface_x", "surface_y", "surface_z"]

# Columns of morphology dataframes
_STR_SEC_ID = "section_id"
_STR_SEG_ID = "segment_id"
_STR_SEG_OFF = "segment_offset"
_STR_SEC_OFF = "section_pos" #!

# Prefix and columns that can be both afferent or efferent
_PF_AFF = "afferent_"
_PF_EFF = "efferent_"
_WITH_DIR = _C_CENTER + _C_SURFACE + [_STR_SEC_ID, _STR_SEG_ID, _STR_SEG_OFF, _STR_SEC_OFF]

# Names of groups in the morphology-w-spines hdf5 file
GRP_EDGES = "edges"
GRP_MORPH = "morphology"
GRP_SPINES = "spines"
GRP_MESHES = "meshes"
GRP_SKELETONS = "skeletons"
GRP_SOMA = "soma"
GRP_VERTICES = "vertices"
GRP_TRIANGLES = "triangles"
GRP_OFFSETS = "offsets"

# Defaults values to fill in for spine-related properties of non-spine synapses
_V_FALLBACK = "_NONE"
_V_DTYPE_DICT = {
    "float64": 0.0,
    "float32": 0.0,
    "int64": -1,
    "int32": -1
}
_V_COLNAME_DICT = {}

def find_nearest_mesh_points(mesh_pt_df, pts):
    tree = KDTree(mesh_pt_df[["x", "y", "z"]])
    dist, idx = tree.query(pts, k=1)
    idx = mesh_pt_df.index[idx]
    res = pandas.concat([
        mesh_pt_df.loc[idx, [_C_SP_INDEX]],
        pandas.DataFrame({"distance": dist},
                         index=idx)
    ], axis=1)
    res.index = pts.index
    return res

def synapse_info_df(client, pt_root_id, resolutions, col_location="ctr_pt_position"):
    if not isinstance(pt_root_id, list):
        pt_root_id = [pt_root_id]
    syns = client.materialize.synapse_query(post_ids=pt_root_id)

    syn_locs = syns[col_location].apply(lambda _x: pandas.Series(_x * resolutions / 1000.0,
                                                                       index=_C_P_LOCS))
    syns = pandas.concat([syns, syn_locs], axis=1).reset_index(drop=True)
    syns.index.name = "synapse_id"
    return syns

def morph_to_segs_df(morph):
    segs = []
    for sec in morph.sections:
        seg_start, seg_end = zip(*sec.segments)
        seg_start = pandas.DataFrame(seg_start, columns=_C_SEG_S_F)
        seg_end = pandas.DataFrame(seg_end, columns=_C_SEG_E_F)
        seg = pandas.concat([seg_start, seg_end], axis=1).reset_index(drop=False).rename(columns={"index": _STR_SEG_ID})
        segs.append(seg)
    segs = pandas.concat(segs, axis=0, keys=range(1, len(segs) + 1), names=[_STR_SEC_ID])
    segs = segs.droplevel(1).reset_index()
    return segs

def morph_to_spine_and_soma_df(m):
    all_spine_points = pandas.concat(
            [pandas.DataFrame(m.spine_mesh_points(i), columns=["x", "y", "z"])
            for i in range(m.spine_count)],
            axis=0, keys=m.spine_table.index.to_numpy(), names=[_C_SP_INDEX]
        ).reset_index(0)
    soma_points = pandas.DataFrame(m.soma_mesh_points, columns=["x", "y", "z"])
    soma_points[_C_SP_INDEX] = -1

    spine_and_soma_points = pandas.concat([all_spine_points, soma_points], axis=0).reset_index(drop=True)
    return spine_and_soma_points

def map_points_to_segs_df(segs, pts):
    chunk_sz = 1000
    if len(pts) <= chunk_sz:
        res = _map_points_to_segs_df(
            segs,
            pts.to_numpy()
            )
    else:
        chunk_ab = numpy.arange(0, len(pts) + chunk_sz, chunk_sz)
        res = []
        for a, b in tqdm.tqdm(list(zip(chunk_ab[:-1], chunk_ab[1:]))):
            res.append(
                _map_points_to_segs_df(
                    segs,
                    pts.iloc[a:b].to_numpy()
                )
            )
        res = pandas.concat(res, axis=0)
    res.index = pts.index
    return res

def _map_points_to_segs_df(segs, pts):
    d_seg = segs[_C_SEG_E].to_numpy() - segs[_C_SEG_S].to_numpy() # vector from starts to ends of all segs
    l_seg = numpy.linalg.norm(d_seg, axis=1) # lengths of segs
    d_seg = d_seg / (l_seg.reshape((-1, 1)) + 1E-15) # normalization. Direction from starts to ends of all segs

    d_spine_seg = pts.reshape((-1, 1, 3)) - segs[_C_SEG_S].values.reshape((1, -1, 3)) #vectors from seg starts to points
    d_spine_segend = pts.reshape((-1, 1, 3)) - segs[_C_SEG_E].values.reshape((1, -1, 3)) #vectors from seg ends to points
    d_spine_seg_l = numpy.linalg.norm(d_spine_seg, axis=-1) # distance from seg starts to points
    d_spine_segend_l = numpy.linalg.norm(d_spine_segend, axis=-1) # distance from seg ends to points
    d_spine_seg = d_spine_seg / (d_spine_seg_l.reshape(d_spine_seg_l.shape + (1,)) + 1E-15) # normalization. Direction from seg starts to points

    cos_spine_seg = (d_spine_seg * d_seg.reshape((1, -1, 3))).sum(axis=-1) # cos of angles between directions to ends and directions to points
    cos_spine_seg = numpy.minimum(numpy.maximum(cos_spine_seg, -1), 1)
    d_spine_seg_proj = cos_spine_seg * d_spine_seg_l # Distance of projection of points onto segs from seg starts

    D = numpy.sin(numpy.arccos(cos_spine_seg)) * d_spine_seg_l # Distance of points from infinite lines defined by segs
    before_start = d_spine_seg_proj < 0
    D[before_start] = d_spine_seg_l[before_start]
    after_end = d_spine_seg_proj > l_seg.reshape((1, -1))
    D[after_end] = d_spine_segend_l[after_end]
    _mpd = numpy.argmin(D, axis=1)

    mpd = segs.iloc[_mpd][[_STR_SEC_ID, _STR_SEG_ID]]
    mpd[_STR_SEG_OFF] = numpy.maximum(numpy.minimum(
        d_spine_seg_proj[range(d_spine_seg_proj.shape[0]), _mpd],
        l_seg[_mpd]
    ), 0.0)
    mpd["distance"] = D[numpy.arange(D.shape[0]), _mpd]

    midx = pandas.MultiIndex.from_frame(mpd[[_STR_SEC_ID, _STR_SEG_ID]])
    r = segs.set_index([_STR_SEC_ID, _STR_SEG_ID]).loc[midx, ["start_d", "end_d"]].mean(axis=1)
    mpd["distance"] -= r.to_numpy()

    return mpd.reset_index(drop=True)

def calc_section_offset(syns, morph, prefix=""):
    try:
        from conntility.subcellular import MorphologyPathDistanceCalculator
    except ImportError:
        raise RuntimeError("Optional dependency Connectome-Utilities not installed!")
    
    PD = MorphologyPathDistanceCalculator(morph.to_morphio())
    all_sec_l = numpy.array([sec.length for sec in morph.sections])
    is_not_on_neurite = syns[prefix + _STR_SEC_ID] < 1

    abs_off = PD.O[syns[prefix + _STR_SEC_ID] - 1, syns[prefix + _STR_SEG_ID]]
    rel_off = (abs_off + syns[prefix + _STR_SEG_OFF]) / all_sec_l[syns[prefix + _STR_SEC_ID] - 1]
    rel_off[is_not_on_neurite] = 0.0
    return numpy.minimum(rel_off, 1.0)

def segment_interpolator(seg, o):
    a, b = seg
    c = b[:3] - a[:3]
    return pandas.Series(
        a[:3] + o * c / numpy.linalg.norm(c),
        index=_C_CENTER
    )

def calc_center_positions(df, morph):
    return df.apply(lambda row: segment_interpolator(morph.section(int(row[_STR_SEC_ID])-1).segments[int(row[_STR_SEG_ID])],
                                              row[_STR_SEG_OFF]),
          axis=1)

def rename_directed_dataframe_colums(df, prefix=_PF_AFF):
    rename_dict = dict([
        (_col, prefix + _col)
        for _col in _WITH_DIR
        if _col in df.columns
    ])
    return df.rename(columns=rename_dict)

def fill_defaults_for_missing_columns(df_reference, df_modify):
    missingcols = [_col for _col in df_reference.columns if _col not in df_modify.columns]
    for _col in missingcols:
        if _col in _V_COLNAME_DICT:
            df_modify[_col] = _V_COLNAME_DICT[_col]
        else:
            df_modify[_col] = _V_DTYPE_DICT.get(str(df_reference.dtypes[_col]), _V_FALLBACK)

def edges_dataframe_for_soma_syns(syns, m, mpd, is_on_soma):
    mapped_syn_idx = syns.index[is_on_soma]
    c = pandas.concat([
            syns.loc[mapped_syn_idx, _C_P_LOCS].rename(columns={
            _C_P_LOCS[0]: _PF_AFF + _C_SURFACE[0],
            _C_P_LOCS[1]: _PF_AFF + _C_SURFACE[1],
            _C_P_LOCS[2]: _PF_AFF + _C_SURFACE[2],
        }),
        syns.loc[mapped_syn_idx, _C_P_LOCS].rename(columns={
            _C_P_LOCS[0]: _PF_AFF + _C_CENTER[0],
            _C_P_LOCS[1]: _PF_AFF + _C_CENTER[1],
            _C_P_LOCS[2]: _PF_AFF + _C_CENTER[2],
        })
    ], axis=1)
    c[_PF_AFF + _STR_SEC_ID] = 0
    c[_PF_AFF + _STR_SEG_ID] = 0
    c[_PF_AFF + _STR_SEG_OFF] = 0.0
    c[_PF_AFF + _STR_SEC_OFF] = calc_section_offset(c, m, prefix=_PF_AFF)
    c["distance"] = mpd.loc[is_on_soma, "distance"]
    return c

def edges_dataframe_for_shaft_syns(syns, m, mpd, is_on_shaft):
    b = pandas.concat([syns.loc[is_on_shaft, _C_P_LOCS].rename(columns=dict(zip(_C_P_LOCS, _C_SURFACE))),
                    mpd.loc[is_on_shaft]], axis=1)
    b = pandas.concat([b, calc_center_positions(b, m)], axis=1)
    b[_STR_SEC_OFF] = calc_section_offset(b, m)
    b = rename_directed_dataframe_colums(b, _PF_AFF)
    return b

def edges_dataframe_for_spine_syns(syns, m, mpd, is_on_spine):
    a = m.spine_table.loc[mpd.loc[is_on_spine, _C_SP_INDEX]].copy()
    a = a.drop(columns=['spine_orientation_vector_x', 'spine_orientation_vector_y',
                        'spine_orientation_vector_z', 'spine_rotation_x',
                        'spine_rotation_y', 'spine_rotation_z', 'spine_rotation_w'])
    a.index.name = _C_SP_INDEX
    a["distance"] = mpd.loc[is_on_spine, "distance"].to_numpy()
    a["synapse_id"] = mpd.index[is_on_spine].to_numpy()
    # a = a.sort_index()
    # a[_C_SHARING_ID] = numpy.cumsum(numpy.hstack([0, numpy.diff(a.index)]) > 0)
    a[_C_PSD_ID] = numpy.arange(len(a.index)) # For now simply all different
    a = a.reset_index(drop=False).set_index("synapse_id").sort_index()
    return a

def map_afferents_to_spiny_morphology(m, syns):
    segs_df = morph_to_segs_df(m)
    spine_and_soma_points = morph_to_spine_and_soma_df(m)

    mpd_nrt = map_points_to_segs_df(segs_df, syns[_C_P_LOCS])
    mpd_spn = find_nearest_mesh_points(spine_and_soma_points, syns[_C_P_LOCS])

    is_on_spine = (mpd_spn["distance"] <= mpd_nrt["distance"]) & (mpd_spn[_C_SP_INDEX] != -1)
    is_on_soma = (mpd_spn["distance"] <= mpd_nrt["distance"]) & (mpd_spn[_C_SP_INDEX] == -1)
    is_on_shaft = (~is_on_spine) & (~is_on_soma)

    df_soma = edges_dataframe_for_soma_syns(syns, m, mpd_spn, is_on_soma)
    df_shaft = edges_dataframe_for_shaft_syns(syns, m, mpd_nrt, is_on_shaft)
    df_spine = edges_dataframe_for_spine_syns(syns, m, mpd_spn, is_on_spine)

    fill_defaults_for_missing_columns(df_spine, df_soma)
    fill_defaults_for_missing_columns(df_spine, df_shaft)

    return pandas.concat([df_soma, df_shaft, df_spine], axis=0).sort_index()
