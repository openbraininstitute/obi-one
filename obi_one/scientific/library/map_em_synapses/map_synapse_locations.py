import numpy  # ruff: ignore[unconventional-import-alias]
import pandas  # ruff: ignore[unconventional-import-alias]
from caveclient import CAVEclient
from morph_spines import MorphologyWithSpines
from neurom.core import Morphology
from scipy.spatial import KDTree

from obi_one.scientific.library.map_em_synapses.constants import (
    C_CAVE_ID_IN,
    C_CAVE_ID_OUT,
    C_CENTER,
    C_P_LOCS,
    C_PSD_ID,
    C_SEG_E,
    C_SEG_E_F,
    C_SEG_S,
    C_SEG_S_F,
    C_SP_INDEX,
    C_SURFACE,
    PF_AFF,
    STR_SEC_ID,
    STR_SEC_OFF,
    STR_SEG_ID,
    STR_SEG_OFF,
    V_COLNAME_DICT,
    V_DTYPE_DICT,
    V_FALLBACK,
    WITH_DIR,
)


def find_nearest_mesh_points(
    mesh_pt_df: pandas.DataFrame, pts: pandas.DataFrame
) -> pandas.DataFrame:
    tree = KDTree(mesh_pt_df[["x", "y", "z"]])
    dist, idx = tree.query(pts, k=1)
    idx = mesh_pt_df.index[idx]
    res = pandas.concat(
        [mesh_pt_df.loc[idx, [C_SP_INDEX]], pandas.DataFrame({"distance": dist}, index=idx)],
        axis=1,
    )
    res.index = pts.index
    return res


def add_competing_mesh_distances(
    mesh_pt_df: pandas.DataFrame, pts: pandas.DataFrame
) -> pandas.Series:
    tree = KDTree(mesh_pt_df[["x", "y", "z"]])
    competitor_dists = pandas.Series(
        -numpy.ones(len(pts)), index=pts.index, name="competing_distance"
    )
    mask = competitor_dists < 0
    mask_idx = competitor_dists[mask].index
    max_k = len(mesh_pt_df)
    k = numpy.minimum(100, max_k)

    while len(mask_idx) > 0:
        dist, idx = tree.query(pts.loc[mask_idx], k=k)
        competitor_ids = mesh_pt_df.spine_sharing_id.to_numpy()[idx]
        is_different = competitor_ids[:, 0] != competitor_ids[:, -1]
        first_different = [
            numpy.nonzero(x)[0][0] + 1
            for x in numpy.diff(competitor_ids[is_different], axis=1) != 0
        ]
        competitor_dists[mask_idx[is_different]] = dist[is_different][
            range(len(first_different)), first_different
        ]

        mask = competitor_dists < 0
        mask_idx = competitor_dists[mask].index
        if k == max_k:
            break
        k = numpy.minimum(k * 4, max_k)
    return competitor_dists


def estimate_mesh_resolution(mesh_pt_df: pandas.DataFrame) -> float:
    tree = KDTree(mesh_pt_df[["x", "y", "z"]])
    dist, _ = tree.query(mesh_pt_df[["x", "y", "z"]], k=2)
    return dist[:, 1].mean()


def synapse_info_df(
    client: CAVEclient, pt_root_id: int, resolutions: list, col_location: str = "ctr_pt_position"
) -> pandas.DataFrame:
    if not isinstance(pt_root_id, list):
        pt_root_id = [pt_root_id]  # ty:ignore[invalid-assignment]
    syns = client.materialize.synapse_query(post_ids=pt_root_id)  # ty:ignore[unresolved-attribute]

    syn_locs = syns[col_location].apply(
        lambda _x: pandas.Series(_x * resolutions / 1000.0, index=C_P_LOCS)
    )
    syns = pandas.concat([syns, syn_locs], axis=1).reset_index(drop=True)
    syns.index.name = "synapse_id"
    return syns


def morph_to_segs_df(morph: MorphologyWithSpines) -> pandas.DataFrame:
    segs = []
    sec_id_keys = []
    for sec in morph.morphology.sections:
        if len(sec.points) <= 1:
            continue
        seg_start, seg_end = zip(*sec.segments, strict=False)
        seg_start = pandas.DataFrame(seg_start, columns=C_SEG_S_F)  # ty:ignore[invalid-argument-type]
        seg_end = pandas.DataFrame(seg_end, columns=C_SEG_E_F)  # ty:ignore[invalid-argument-type]
        seg = (
            pandas.concat([seg_start, seg_end], axis=1)
            .reset_index(drop=False)
            .rename(columns={"index": STR_SEG_ID})
        )
        segs.append(seg)
        sec_id_keys.append(sec.id + 1)
    segs = pandas.concat(segs, axis=0, keys=sec_id_keys, names=[STR_SEC_ID])
    segs = segs.droplevel(1).reset_index()
    return segs


def morph_to_spine_and_soma_df(m: MorphologyWithSpines) -> pandas.DataFrame:
    all_spine_points = pandas.concat(
        [
            pandas.DataFrame(m.spines.spine_mesh_points(i), columns=["x", "y", "z"]).dropna()  # ty:ignore[invalid-argument-type]
            for i in range(m.spines.spine_count)
        ],
        axis=0,
        keys=m.spines.spine_table.index.to_numpy(),
        names=[C_SP_INDEX],
    ).reset_index(0)
    soma_points = pandas.DataFrame(m.soma.soma_mesh_points, columns=["x", "y", "z"]).dropna()  # ty:ignore[invalid-argument-type]
    soma_points[C_SP_INDEX] = -1

    spine_and_soma_points = pandas.concat([all_spine_points, soma_points], axis=0).reset_index(
        drop=True
    )
    return spine_and_soma_points


def map_points_to_segs_df(segs: pandas.DataFrame, pts: pandas.DataFrame) -> pandas.DataFrame:
    chunk_sz = 250
    if len(pts) <= chunk_sz:
        res = _map_points_to_segs_df(segs, pts.to_numpy())
    else:
        chunk_ab = numpy.arange(0, len(pts) + chunk_sz, chunk_sz)
        res = []
        for a, b in zip(chunk_ab[:-1], chunk_ab[1:], strict=False):  # ruff: ignore[zip-instead-of-pairwise]
            res.append(_map_points_to_segs_df(segs, pts.iloc[a:b].to_numpy()))
        res = pandas.concat(res, axis=0)
    res.index = pts.index
    return res


def _map_points_to_segs_df(segs: pandas.DataFrame, pts: numpy.ndarray) -> pandas.DataFrame:
    d_seg = (
        segs[C_SEG_E].to_numpy() - segs[C_SEG_S].to_numpy()
    )  # vector from starts to ends of all segs
    l_seg = numpy.linalg.norm(d_seg, axis=1)  # lengths of segs
    d_seg /= l_seg.reshape((-1, 1)) + 1e-15
    # normalization. Direction from starts to ends of all segs

    d_spine_seg = pts.reshape((-1, 1, 3)) - segs[C_SEG_S].to_numpy().reshape(
        (1, -1, 3)
    )  # vectors from seg starts to points
    d_spine_segend = pts.reshape((-1, 1, 3)) - segs[C_SEG_E].to_numpy().reshape(
        (1, -1, 3)
    )  # vectors from seg ends to points
    d_spine_seg_l = numpy.linalg.norm(d_spine_seg, axis=-1)  # distance from seg starts to points
    d_spine_segend_l = numpy.linalg.norm(
        d_spine_segend, axis=-1
    )  # distance from seg ends to points
    d_spine_seg /= d_spine_seg_l.reshape((*d_spine_seg_l.shape, 1)) + 1e-15
    # normalization. Direction from seg starts to points

    cos_spine_seg = (d_spine_seg * d_seg.reshape((1, -1, 3))).sum(
        axis=-1
    )  # cos of angles between directions to ends and directions to points
    cos_spine_seg = numpy.minimum(numpy.maximum(cos_spine_seg, -1), 1)
    d_spine_seg_proj = (
        cos_spine_seg * d_spine_seg_l
    )  # Distance of projection of points onto segs from seg starts

    dists_arr = (
        numpy.sin(numpy.arccos(cos_spine_seg)) * d_spine_seg_l
    )  # Distance of points from infinite lines defined by segs
    before_start = d_spine_seg_proj < 0
    dists_arr[before_start] = d_spine_seg_l[before_start]
    after_end = d_spine_seg_proj > l_seg.reshape((1, -1))
    dists_arr[after_end] = d_spine_segend_l[after_end]
    mpd_ = numpy.argmin(dists_arr, axis=1)

    mpd = segs.iloc[mpd_][[STR_SEC_ID, STR_SEG_ID]]
    mpd[STR_SEG_OFF] = numpy.maximum(
        numpy.minimum(d_spine_seg_proj[range(d_spine_seg_proj.shape[0]), mpd_], l_seg[mpd_]), 0.0
    )
    mpd["distance"] = dists_arr[numpy.arange(dists_arr.shape[0]), mpd_]

    midx = pandas.MultiIndex.from_frame(mpd[[STR_SEC_ID, STR_SEG_ID]])
    r = segs.set_index([STR_SEC_ID, STR_SEG_ID]).loc[midx, ["start_d", "end_d"]].mean(axis=1)
    mpd["distance"] -= r.to_numpy()

    return mpd.reset_index(drop=True)


def calc_section_offset(
    syns: pandas.DataFrame, morph: Morphology, prefix: str = ""
) -> numpy.ndarray:
    try:
        from conntility.subcellular import (  # ruff: ignore[import-outside-top-level]
            MorphologyPathDistanceCalculator,
        )
    except ImportError:
        err_str = "Optional dependency Connectome-Utilities not installed!"
        raise RuntimeError(err_str) from None

    pd_calc = MorphologyPathDistanceCalculator(morph.to_morphio())
    all_sec_l = numpy.array([sec.length for sec in morph.sections])
    is_not_on_neurite = syns[prefix + STR_SEC_ID] < 1

    abs_off = pd_calc.offset[syns[prefix + STR_SEC_ID] - 1, syns[prefix + STR_SEG_ID]]
    rel_off = (abs_off + syns[prefix + STR_SEG_OFF]) / all_sec_l[syns[prefix + STR_SEC_ID] - 1]
    rel_off[is_not_on_neurite] = 0.0
    return numpy.minimum(rel_off, 1.0)


def segment_interpolator(seg: tuple, o: float) -> pandas.Series:
    a, b = seg
    c = b[:3] - a[:3]
    return pandas.Series(a[:3] + o * c / numpy.linalg.norm(c), index=C_CENTER)


def calc_center_positions(df: pandas.DataFrame, morph: Morphology) -> pandas.DataFrame:
    return df.apply(
        lambda row: segment_interpolator(
            morph.section(int(row[STR_SEC_ID]) - 1).segments[int(row[STR_SEG_ID])],
            row[STR_SEG_OFF],
        ),
        axis=1,
    )


def rename_directed_dataframe_colums(
    df: pandas.DataFrame, prefix: str = PF_AFF
) -> pandas.DataFrame:
    rename_dict = {col: prefix + col for col in WITH_DIR if col in df.columns}
    return df.rename(columns=rename_dict)


def fill_defaults_for_missing_columns(
    df_reference: pandas.DataFrame, df_modify: pandas.DataFrame
) -> None:
    missingcols = [col for col in df_reference.columns if col not in df_modify.columns]
    for col in missingcols:
        if col in V_COLNAME_DICT:
            df_modify[col] = V_COLNAME_DICT[col]
        else:
            df_modify[col] = V_DTYPE_DICT.get(str(df_reference.dtypes[col]), V_FALLBACK)


def edges_dataframe_for_soma_syns(
    syns: pandas.DataFrame,
    m: MorphologyWithSpines,
    mpd: pandas.DataFrame,
    is_on_soma: pandas.Series,
) -> pandas.DataFrame:
    mapped_syn_idx = syns.index[is_on_soma]
    c = pandas.concat(
        [
            syns.loc[mapped_syn_idx, [C_CAVE_ID_IN, *C_P_LOCS]].rename(
                columns={
                    C_P_LOCS[0]: C_SURFACE[0],
                    C_P_LOCS[1]: C_SURFACE[1],
                    C_P_LOCS[2]: C_SURFACE[2],
                    C_CAVE_ID_IN: C_CAVE_ID_OUT,
                }
            ),
            syns.loc[mapped_syn_idx, C_P_LOCS],
        ],
        axis=1,
    )
    c[STR_SEC_ID] = 0
    c[STR_SEG_ID] = 0
    c[STR_SEG_OFF] = 0.0
    c[STR_SEC_OFF] = calc_section_offset(c, m.morphology)
    for col, coord in zip(C_CENTER, m.morphology.soma.center, strict=False):
        c[col] = coord
    c["distance"] = mpd.loc[is_on_soma, "distance"]
    c = rename_directed_dataframe_colums(c, prefix=PF_AFF)
    return c


def edges_dataframe_for_shaft_syns(
    syns: pandas.DataFrame,
    m: MorphologyWithSpines,
    mpd: pandas.DataFrame,
    is_on_shaft: pandas.Series,
) -> pandas.DataFrame:
    b = pandas.concat(
        [
            syns.loc[is_on_shaft, C_P_LOCS],
            syns.loc[is_on_shaft, [C_CAVE_ID_IN, *C_P_LOCS]].rename(
                columns={
                    C_P_LOCS[0]: C_SURFACE[0],
                    C_P_LOCS[1]: C_SURFACE[1],
                    C_P_LOCS[2]: C_SURFACE[2],
                    C_CAVE_ID_IN: C_CAVE_ID_OUT,
                }
            ),
            mpd.loc[is_on_shaft],
        ],
        axis=1,
    )
    b = pandas.concat([b, calc_center_positions(b, m.morphology)], axis=1)
    b[STR_SEC_OFF] = calc_section_offset(b, m.morphology)
    b = rename_directed_dataframe_colums(b, PF_AFF)
    return b


def edges_dataframe_for_spine_syns(
    syns: pandas.DataFrame,
    m: MorphologyWithSpines,
    mpd: pandas.DataFrame,
    is_on_spine: pandas.Series,
) -> pandas.DataFrame:
    a = m.spines.spine_table.loc[mpd.loc[is_on_spine, C_SP_INDEX]].copy()
    a = a.drop(
        columns=[
            "spine_orientation_vector_x",
            "spine_orientation_vector_y",
            "spine_orientation_vector_z",
            "spine_rotation_x",
            "spine_rotation_y",
            "spine_rotation_z",
            "spine_rotation_w",
        ]
    )
    a.index.name = C_SP_INDEX
    a["distance"] = mpd.loc[is_on_spine, "distance"].to_numpy()
    a["synapse_id"] = mpd.index[is_on_spine].to_numpy()
    a[C_PSD_ID] = numpy.arange(len(a.index))  # For now simply all different
    for col in C_P_LOCS:
        a[PF_AFF + col] = syns.loc[
            is_on_spine, col
        ].to_numpy()  # Could also be a pandas.concat after reset_index()
    a[C_CAVE_ID_OUT] = syns.loc[is_on_spine, C_CAVE_ID_IN].to_numpy()
    a = a.reset_index(drop=False).set_index("synapse_id").sort_index()
    return a


def map_afferents_to_spiny_morphology(
    m: MorphologyWithSpines,
    syns: pandas.DataFrame,
    add_quality_info: bool = False,  # ruff: ignore[boolean-type-hint-positional-argument, boolean-default-value-positional-argument]
) -> tuple[pandas.DataFrame, float | None]:
    segs_df = morph_to_segs_df(m)
    spine_and_soma_points = morph_to_spine_and_soma_df(m)

    mpd_nrt = map_points_to_segs_df(segs_df, syns[C_P_LOCS])
    mpd_spn = find_nearest_mesh_points(spine_and_soma_points, syns[C_P_LOCS])

    is_on_spine = (mpd_spn["distance"] <= mpd_nrt["distance"]) & (mpd_spn[C_SP_INDEX] != -1)
    is_on_soma = (mpd_spn["distance"] <= mpd_nrt["distance"]) & (mpd_spn[C_SP_INDEX] == -1)
    is_on_shaft = (~is_on_spine) & (~is_on_soma)

    df_soma = edges_dataframe_for_soma_syns(syns, m, mpd_spn, is_on_soma)
    df_shaft = edges_dataframe_for_shaft_syns(syns, m, mpd_nrt, is_on_shaft)
    df_spine = edges_dataframe_for_spine_syns(syns, m, mpd_spn, is_on_spine)

    fill_defaults_for_missing_columns(df_spine, df_soma)
    fill_defaults_for_missing_columns(df_spine, df_shaft)

    df_concat = pandas.concat([df_soma, df_shaft, df_spine], axis=0).sort_index()

    if add_quality_info:
        competing_dist = add_competing_mesh_distances(spine_and_soma_points, syns[C_P_LOCS])
        competing_dist[is_on_shaft] = mpd_spn.loc[is_on_shaft, "distance"]
        competing_dist[is_on_soma] = numpy.minimum(
            competing_dist[is_on_soma].to_numpy(), mpd_nrt.loc[is_on_soma, "distance"].to_numpy()
        )
        competing_dist[is_on_spine] = numpy.minimum(
            competing_dist[is_on_spine].to_numpy(), mpd_nrt.loc[is_on_spine, "distance"].to_numpy()
        )
        df_concat["competing_distance"] = competing_dist
        return df_concat, estimate_mesh_resolution(spine_and_soma_points)
    return df_concat, None
