import logging.handlers
import numpy
import json
import conntility
import neurom.io
import connalysis
import neurom.io.utils
import pandas
import h5py
import os
import logging

from scipy.spatial.transform import Rotation

_C_P_LOCS = ["post_x", "post_y", "post_z"]
_PF_PRE = "pre_"
_PF_POST = "post_"
_STR_EXT = "extrinsic"
_C_SEG_S = ["start_x", "start_y", "start_z"]
_C_SEG_S_F = _C_SEG_S + ["start_d"]
_C_SEG_E = ["end_x", "end_y", "end_z"]
_C_SEG_E_F = _C_SEG_E + ["end_d"]
_STR_SEC_ID = "sec_id"
_STR_SEG_ID = "seg_id"
_STR_SPINE_ID = "spine_id"
_STR_SYN_ID = "syn_id"
_STR_SEG_OFF = "seg_off"
_STR_SEC_OFF = "sec_off"
_STR_SPINE_X = "spine_pos_x"
_STR_SPINE_Y = "spine_pos_y"
_STR_SPINE_Z = "spine_pos_z"

_STR_PRE_NODE = _PF_PRE + "node_id"
_STR_POST_NODE = _PF_POST + "node_id"

L = logging.getLogger(__name__)
L.setLevel(logging.INFO)
handler = logging.handlers.RotatingFileHandler(
    'EMEdgesToSonata.log',          # Log file name
    maxBytes=10000000,    # Maximum size of a log file in bytes before rotation
    backupCount=3       # Number of backup files to keep
)
L.addHandler(handler)


def synapse_info_from_h5_dump(fn, pt_root_ids, name_pat="post_pt_root_id_{0}"):
    names = [name_pat.format(_id) for _id in pt_root_ids]
    dfs = []
    for _name in names:
        dfs.append(pandas.read_hdf(fn, _name))
    return pandas.concat(dfs, axis=0).reset_index(drop=True)

def synapse_info_df(client, pt_root_id, resolutions, col_location="ctr_pt_position"):
    if not isinstance(pt_root_id, list):
        pt_root_id = [pt_root_id]
    syns = client.materialize.synapse_query(post_ids=pt_root_id)

    syn_locs = syns[col_location].apply(lambda _x: pandas.Series(_x * resolutions / 1000.0,
                                                                       index=_C_P_LOCS))
    syns = pandas.concat([syns, syn_locs], axis=1)
    return syns

def synapse_info_df_from_local_file(pt_root_id, resolutions, h5_fn, dset_name_pat="post_pt_root_id_{0}"):
    if not isinstance(pt_root_id, list):
        pt_root_id = [pt_root_id]
    df = pandas.concat([
        pandas.read_hdf(h5_fn, dset_name_pat.format(_id))
        for _id in pt_root_id
    ], axis=0).reset_index(drop=True)
    for _col_in, _col_out, _res in zip(["x", "y", "z"], _C_P_LOCS, resolutions):
        df[_col_out] = df[_col_in] * _res / 1000.0
    return df

def combined_synape_info(df_syns, df_cells, cols_cells):
    for _col in cols_cells:
        _v = df_cells[_col].reindex(df_syns["pre_pt_root_id"], fill_value=_STR_EXT).values
        df_syns[_PF_PRE + _col] = _v

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

def map_points_to_segs_df(segs, pts, soma_center=None, soma_radius=None, seg_end_buf=0.1, soma_buf=0.1, max_dist=4.0):
    chunk_sz = 1000
    if len(pts) <= chunk_sz:
        res = _map_points_to_segs_df(
            segs,
            pts,
            soma_center=soma_center, soma_radius=soma_radius,
            seg_end_buf=seg_end_buf, soma_buf=soma_buf, max_dist=max_dist
            )
    else:
        chunk_ab = numpy.arange(0, len(pts) + chunk_sz, chunk_sz)
        res = []
        for a, b in zip(chunk_ab[:-1], chunk_ab[1:]):
            res.append(
                _map_points_to_segs_df(
                    segs,
                    pts[a:b],
                    soma_center=soma_center, soma_radius=soma_radius,
                    seg_end_buf=seg_end_buf, soma_buf=soma_buf, max_dist=max_dist
                )
            )
        res = pandas.concat(res, axis=0).reset_index(drop=True)
    assert len(res) == len(pts)
    return res

def _map_points_to_segs_df(segs, pts, soma_center=None, soma_radius=None, seg_end_buf=0.1, soma_buf=0.1, max_dist=4.0):
    d_seg = segs[_C_SEG_E].values - segs[_C_SEG_S].values
    l_seg = numpy.linalg.norm(d_seg, axis=1)
    d_seg = d_seg / l_seg.reshape((-1, 1))

    d_spine_seg = pts.reshape((-1, 1, 3)) - segs[_C_SEG_S].values.reshape((1, -1, 3))
    d_spine_seg_l = numpy.linalg.norm(d_spine_seg, axis=-1)
    d_spine_seg = d_spine_seg / d_spine_seg_l.reshape(d_spine_seg_l.shape + (1,))

    cos_spine_seg = (d_spine_seg * d_seg.reshape((1, -1, 3))).sum(axis=-1)
    cos_spine_seg = numpy.minimum(numpy.maximum(cos_spine_seg, -1), 1)
    d_spine_seg_proj = cos_spine_seg * d_spine_seg_l

    a = 1 + seg_end_buf; b = -seg_end_buf
    A = (d_spine_seg_proj < (a * l_seg.reshape((1, -1)))) & (d_spine_seg_proj > (b * l_seg.reshape((1, -1))))
    D = numpy.sin(numpy.arccos(cos_spine_seg)) * d_spine_seg_l
    D[~A] = 1E12
    _mpd = numpy.argmin(D, axis=1)

    mpd = segs.iloc[_mpd][[_STR_SEC_ID, _STR_SEG_ID]]
    mpd[_STR_SEG_OFF] = numpy.maximum(numpy.minimum(
        d_spine_seg_proj[range(d_spine_seg_proj.shape[0]), _mpd],
        l_seg[_mpd]
    ), 0.0)
    invalid = D[numpy.arange(D.shape[0]), _mpd] > max_dist
    mpd[invalid] = -1

    if soma_center is not None:
        if soma_radius is None:
            soma_radius = max_dist
        on_soma = numpy.linalg.norm(pts - soma_center, axis=1) < ((soma_buf + 1) * soma_radius)
        mpd[on_soma] = 0
    return mpd.reset_index(drop=True)

def calc_section_offset(syns, morph):
    try:
        from conntility.subcellular import MorphologyPathDistanceCalculator
    except ImportError:
        raise RuntimeError("Optional dependency Connectome-Utilities not installed!")
    
    PD = MorphologyPathDistanceCalculator(morph.to_morphio())
    all_sec_l = numpy.array([sec.length for sec in morph.sections])
    is_not_on_neurite = syns[_STR_SEC_ID] < 1

    abs_off = PD.O[syns[_STR_SEC_ID] - 1, syns[_STR_SEG_ID]]
    rel_off = (abs_off + syns[_STR_SEG_OFF]) / all_sec_l[syns[_STR_SEC_ID] - 1]
    rel_off[is_not_on_neurite] = 0.0
    return numpy.minimum(rel_off, 1.0)

def map_points_to_spines(spine_pos, spine_orient, pts, max_dist=4.0, mx_per_pos=1, mx_per_spine=2):
    orient_n = spine_orient / numpy.linalg.norm(spine_orient, axis=1, keepdims=True)

    pw_d_xyz = pts.values.reshape((-1, 1, 3)) - spine_pos.reshape((1, -1, 3))  # syns X spines
    surf_dist = numpy.sqrt(numpy.sum(pw_d_xyz ** 2, axis=-1))

    # syn - spine combinations where the synapse is close enough
    nz_syn, nz_spine = numpy.nonzero(surf_dist < max_dist)

    cand_pw_d = pw_d_xyz[nz_syn, nz_spine]
    cand_pw_d = cand_pw_d / numpy.linalg.norm(cand_pw_d, axis=1, keepdims=True)
    cand_align = numpy.sum(cand_pw_d * orient_n[nz_spine], axis=1)

    # For all candidates, i.e., synapses that are close enough to a spine,
    # we calculate how well the location of the synapse aligns with the overall
    # direction of the spine
    C = pandas.DataFrame({
    "cos_angle": cand_align, 
    _STR_SYN_ID: nz_syn, 
    _STR_SPINE_ID: nz_spine
    })
    C = C.sort_values("cos_angle", ascending=False)

    # Greedy mapping: We start with the best alignment and move on to the next best,
    # etc. 
    mapped = []
    syn_m_counts = {}
    spine_m_counts = {}
    while True:
        # Stop mapping if everything is mapped ...
        if len(C) == 0:
            break
        # or if the alignment is poor (values are sorted).
        if C.iloc[0]["cos_angle"] < 0.0:
            break

        mapped.append(C[[_STR_SYN_ID, _STR_SPINE_ID]].iloc[0])
        _syn = C[_STR_SYN_ID].iloc[0]; _spine = C[_STR_SPINE_ID].iloc[0]
        syn_m_counts[_syn] = syn_m_counts.get(_syn, 0) + 1 
        spine_m_counts[_spine] = spine_m_counts.get(_spine, 0) + 1
        keep = numpy.ones(len(C), dtype=bool)

        if syn_m_counts[_syn] >= mx_per_pos:
            keep = keep & (C[_STR_SYN_ID] != C.iloc[0][_STR_SYN_ID])

        if spine_m_counts[_spine] >= mx_per_spine:
            keep = keep & (C[_STR_SPINE_ID] != C.iloc[0][_STR_SPINE_ID])
        C = C.loc[keep]
    
    if len(mapped) == 0:
        return pandas.DataFrame({
            _STR_SYN_ID: [],
            _STR_SPINE_ID: [],
            _STR_SPINE_X: [],
            _STR_SPINE_Y: [],
            _STR_SPINE_Z: []
        })
    mapped = pandas.concat(mapped, axis=1).transpose()
    mapped_pos = spine_pos[mapped[_STR_SPINE_ID].values]
    mapped[_STR_SPINE_X] = mapped_pos[:, 0]
    mapped[_STR_SPINE_Y] = mapped_pos[:, 1]
    mapped[_STR_SPINE_Z] = mapped_pos[:, 2]

    return mapped.reset_index(drop=True)

def dummy_mapping_without_morphology(syns):
    syns[_STR_SEC_ID] = numpy.zeros(len(syns), dtype=int)
    syns[_STR_SEG_ID] = numpy.zeros(len(syns), dtype=int)
    syns[_STR_SPINE_ID] = -numpy.ones(len(syns), dtype=int)
    syns[_STR_SEG_OFF] = numpy.zeros(len(syns), dtype=int)
    syns[_STR_SEC_OFF] = numpy.zeros(len(syns), dtype=int)
    syns[_STR_SPINE_X] = -numpy.ones(len(syns), dtype=float)
    syns[_STR_SPINE_Y] = -numpy.ones(len(syns), dtype=float)
    syns[_STR_SPINE_Z] = -numpy.ones(len(syns), dtype=float)
    return syns

def map_synapses_onto_spiny_morphology(syns, morph, spine_dend_pos, spine_srf_pos, spine_orient):
    segs = morph_to_segs_df(morph)
    L.debug("Mapping spines to morphology...")
    spines_on_morph = map_points_to_segs_df(segs, spine_dend_pos).reset_index(drop=True)
    
    # cols syn_id, spine_id, spine_pos_x, spine_pos_y, spine_pos_z. Only where spine is found
    L.debug("Mapping synapses to spines...")
    syns_on_spines = map_points_to_spines(spine_srf_pos, spine_orient, syns[_C_P_LOCS]).reset_index(drop=True)
    # cols syn_id, spine_id, [x, y, z], sec_id, seg_id, seg_off. Only where spine is found
    syns_on_spines = pandas.concat([syns_on_spines,
                spines_on_morph.loc[syns_on_spines[_STR_SPINE_ID]].reset_index(drop=True)
    ], axis=1)

    # cols spine_id, sec_id, seg_id, seg_off. Outside of spine: -1
    mapped = syns_on_spines.set_index(_STR_SYN_ID, drop=True).reindex(index=range(len(syns)), fill_value=-1)
    syns = pandas.concat([syns, mapped], axis=1)

    shaft_syn_locs = syns.loc[syns[_STR_SPINE_ID] == -1][_C_P_LOCS]
    L.debug("Mapping remaining synapses to shafts...")
    syns_on_morph = map_points_to_segs_df(segs,
                                        shaft_syn_locs.values,
                                        soma_center=morph.soma.center,
                                        soma_radius=morph.soma.radius,
                                        seg_end_buf=0.25,
                                        soma_buf=0.2,
                                        max_dist=10.0
    ).set_index(shaft_syn_locs.index)
    L.debug("Mapping done!")
    L.info(f"Ran mapping for {len(syns)} synapses. {len(syns_on_morph)} on shafts.")

    syns.loc[shaft_syn_locs.index, _STR_SEC_ID] = syns_on_morph[_STR_SEC_ID]
    syns.loc[shaft_syn_locs.index, _STR_SEG_ID] = syns_on_morph[_STR_SEG_ID]
    syns.loc[shaft_syn_locs.index, _STR_SEG_OFF] = syns_on_morph[_STR_SEG_OFF]
    syns[_STR_SEC_OFF] = calc_section_offset(syns, morph)
    return syns


def map_to_pt_root_ids(existing_ids, ids_to_map):
    # index: pt_roo_id. All unique. Values: 0-n
    existing_mapping = existing_ids.reset_index().set_index("pt_root_id")["index"]
    # index: existing_ids.index, not all unique. values: bool
    is_contained = ids_to_map.isin(existing_ids)

    mapped = existing_mapping[ids_to_map[is_contained]]
    mapped.index = is_contained[is_contained].index
    return mapped, is_contained


def map_and_extend_mapping(existing_ids, ids_to_map):
    mapped, is_contained = map_to_pt_root_ids(existing_ids, ids_to_map)

    new_ids = ids_to_map[~is_contained].drop_duplicates()
    new_ids.index = pandas.RangeIndex(len(existing_ids), len(existing_ids) + len(new_ids))
    new_mapping = new_ids.reset_index().set_index(ids_to_map.name)["index"]

    mapped_ext = new_mapping[ids_to_map[~is_contained]]
    mapped_ext.index = is_contained[~is_contained].index

    mapped = pandas.concat([mapped, mapped_ext], axis=0).sort_index()
    return mapped, new_ids


def pt_root_to_sonata_id(syns, morphology_ids, intrinsic_ids, virtual_ids, extrinsic_ids):
    syns = syns.reset_index(drop=True)
    # Resolve postsynaptic ids
    post_node_ids, cntnd = map_to_pt_root_ids(intrinsic_ids, syns["post_pt_root_id"])
    # They must be all intrinsic
    assert cntnd.all()

    # Try to resolve presynaptic ids
    pre_node_ids_intrinsic, is_intrinsic = map_to_pt_root_ids(intrinsic_ids, syns["pre_pt_root_id"]) 
    # Next, try to resolve them as part of the virtual population
    pre_node_ids_virtual, is_virtual = map_to_pt_root_ids(virtual_ids, syns["pre_pt_root_id"])
    # If a source is intrinsic it cannot be virtual. Those populations should not overlap
    assert (is_virtual & is_intrinsic).sum() == 0
    neither_v_nor_i = ~is_intrinsic & ~is_virtual
    # The ones that are not resolved are extrinsic and are resolved against that population.
    # In doing so, new extrinsic nodes may be created.
    extrinsic_syns = syns.loc[neither_v_nor_i]
    # Extrinics are only interesting for neurons with morphologies
    # print(extrinsic_syns["post_pt_root_id"].isin(morphology_ids.values).mean())
    extrinsic_syns = extrinsic_syns.loc[extrinsic_syns["post_pt_root_id"].isin(morphology_ids.values)]
    pre_node_ids_extrinsic, new_extrinsics = map_and_extend_mapping(extrinsic_ids, extrinsic_syns["pre_pt_root_id"])

    intrinsic_syns = syns.loc[pre_node_ids_intrinsic.index]
    intrinsic_syns["pre_node_id"] = pre_node_ids_intrinsic
    intrinsic_syns["post_node_id"] = post_node_ids[pre_node_ids_intrinsic.index]

    virtual_syns = syns.loc[pre_node_ids_virtual.index]
    virtual_syns["pre_node_id"] = pre_node_ids_virtual
    virtual_syns["post_node_id"] = post_node_ids[pre_node_ids_virtual.index]

    extrinsic_syns = syns.loc[pre_node_ids_extrinsic.index]
    extrinsic_syns["pre_node_id"] = pre_node_ids_extrinsic
    extrinsic_syns["post_node_id"] = post_node_ids[pre_node_ids_extrinsic.index]

    new_extrinsics.name = "pt_root_id"
    new_extrinsics = pandas.concat([new_extrinsics], axis=1)

    return intrinsic_syns, virtual_syns, extrinsic_syns, new_extrinsics


def format_for_edges_output(syns, columns_to_rename=("id", "size")):
    from obi_one.scientific.microns_to_sonata.utils_nodes import (
        _PREF_SRC
    )

    synapse_col_renaming = {
        _C_P_LOCS[0]: "afferent_synapse_x",
        _C_P_LOCS[1]: "afferent_synapse_y",
        _C_P_LOCS[2]: "afferent_synapse_z",
        _STR_SEC_ID: "afferent_section_id",
        _STR_SEG_ID: "afferent_segment_id",
        _STR_SEG_OFF: "afferent_segment_offset",
        _STR_SEC_OFF: "afferent_section_offset",
        _STR_SPINE_X: "afferent_surface_x",
        _STR_SPINE_Y: "afferent_surface_y",
        _STR_SPINE_Z: "afferent_surface_z",
    }
    for _col in columns_to_rename:
        synapse_col_renaming[_col] = _PREF_SRC + _col
    
    cols_keep = [_STR_SPINE_ID]
    cols_keep = cols_keep + list(synapse_col_renaming.keys())

    syn_props = syns[cols_keep].rename(columns=synapse_col_renaming)
    syn_maps = syns[[_STR_PRE_NODE, _STR_POST_NODE]]
    return syn_maps, syn_props

def find_edges_resume_point(intrinsics, intrinsic_edges_fn, intrinsic_edge_pop_name, with_morphologies=True):
    from .utils_nodes import _STR_NONE, _STR_MORPH

    if os.path.isfile(intrinsic_edges_fn):
        with h5py.File(intrinsic_edges_fn, "r") as h5:
            node_ranges = h5["edges"][intrinsic_edge_pop_name]["indices/target_to_source/node_id_to_ranges"][:]
            assert len(node_ranges) == len(intrinsics), "Invalid edge poplation index!"
            # Nodes without edges so far
            intrinsics = intrinsics.loc[numpy.diff(node_ranges, axis=1)[:, 0] == 0]
    if with_morphologies:
        # Nodes with associated morphologies
        return intrinsics.loc[intrinsics[_STR_MORPH] != _STR_NONE]
    return intrinsics