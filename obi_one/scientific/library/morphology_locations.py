import warnings

import morphio
import numpy as np
import pandas  # noqa: ICN001
import pandas as pd
from scipy import stats
from scipy.stats._distn_infrastructure import rv_frozen

try:
    from conntility.subcellular import MorphologyPathDistanceCalculator
except ImportError:
    warnings.warn("Connectome functionalities not available", UserWarning, stacklevel=1)

_SEC_ID = "section_id"
_SEG_ID = "segment_id"
_SEG_OFF = "segment_offset"
_SEG_LEN = "segment_length"
_SEC_TYP = "section_type"
_SEC_LOC = "normalized_section_offset"
_SOM_PAD = "path_distance"
_CEN_IDX = "reference_loc_index"
_SEG_MIN = "min_seg_offset"
_SEG_MAX = "max_seg_offset"
_PRE_IDX = "source_index"


def path_distance_all_segments_from(
    locs_ref: pd.DataFrame,
    m: morphio.Morphology,
    path_distance_calculator: MorphologyPathDistanceCalculator,
    normalized_seg_loc: float = 0.5,
    lst_sec_types: list | None = None,
) -> pandas.DataFrame:
    """Path distances from reference locations to all segments of a morphology.

    Calculates path distances from reference locations on a morphology to all segments of the
    same morphology.

    Args:
        locs_ref (pd.DataFrame): Defines the reference locations. For details how, see
        conntility.subcellular.MorphologyPathDistanceCalculator.
        m (morphio.Morphology): Morphology to use.
        path_distance_calculator (conntility.subcellular.MorphologyPathDistanceCalculator): \
            Path distance calculator
        must be created on morphology m.
        normalized_seg_loc (float, default: 0.5): Between 0 and 1. Normalized segment location.
        Path distances will be calculated to the part of each segment.
        lst_sec_types (list, default=None): List of section types to consider.
        If None, all types are considered.
    """
    kwargs = {"str_section_id": _SEC_ID, "str_segment_id": _SEG_ID, "str_offset": _SEG_OFF}
    locs_all = pd.concat(
        [
            pd.DataFrame(
                {
                    _SEG_ID: np.arange(m.sections[i].n_points - 1),
                    _SEC_ID: np.ones(m.sections[i].n_points - 1, dtype=int) * (i + 1),
                    _SEC_TYP: np.ones(m.sections[i].n_points - 1, dtype=int)
                    * int(m.sections[i].type),
                    _SEG_LEN: np.linalg.norm(np.diff(m.sections[i].points, axis=0), axis=1),
                }
            )
            for i in range(len(m.sections))
        ],
        axis=0,
    ).reset_index(drop=True)
    if lst_sec_types is not None:
        locs_all = locs_all.loc[locs_all[_SEC_TYP].isin(lst_sec_types)].reset_index(drop=True)
    locs_all[_SEG_OFF] = normalized_seg_loc * locs_all[_SEG_LEN]

    path_distances = path_distance_calculator.path_distances(locs_ref, locs_all, **kwargs)
    path_distances = [
        pd.Series(_path_distances, name=_SOM_PAD) for _path_distances in path_distances
    ]

    return pd.concat(
        [pd.concat([locs_all, _path_distances], axis=1) for _path_distances in path_distances],
        axis=0,
        keys=range(len(path_distances)),
        names=[_CEN_IDX],
    )


def select_segments_as_cluster_centers(
    n_pick: int, locs: pandas.DataFrame, distr: rv_frozen, lst_sec_types: list | None = None
) -> pandas.DataFrame:
    p = distr.pdf(locs[_SOM_PAD])
    if lst_sec_types is not None:
        p = p * locs[_SEC_TYP].isin(lst_sec_types).astype(float)  # noqa: PLR6104

    selected_ids = np.random.choice(locs.index, n_pick, p=p / p.sum())  # noqa: NPY002
    return locs.iloc[selected_ids]


def find_normalized_interval_below_zero(a: float, b: float) -> tuple[float, float]:
    """Find sub-interval of [0, 1] where f is < 0.

    Being given a and b, and assuming f(0) = a, f(1) = b, this function calculates the
    sub-interval of [0, 1] where f is < 0.

    Args:
        a (float): f(0)
        b (float): f(1)
    """
    min_norm_path_distances = float(0)
    max_norm_path_distances = float(1)
    if (b - a) > 0:  # becomes invalid near the end
        max_norm_path_distances = np.minimum(-a / (b - a), max_norm_path_distances)
    elif (b - a) == 0:
        max_norm_path_distances = 0.0
    else:
        min_norm_path_distances = np.maximum(-a / (b - a), min_norm_path_distances)
    return min_norm_path_distances, max_norm_path_distances


def min_max_offset_in_segment(row: pd.Series, max_distance: float) -> pd.Series:
    """Determines offsets from segment starting point closer than max_distance. \

    Determines which offsets from the starting point of a segment are closer in path distance \
        than a specified maximum value.

    Args:
        row (pd.Series): Must specify path distance at the start and end of the segment,
        plus the length of the segment. For the names of the corresponding entries check the code.
        max_distance (float): Maximum path distance allowed.
    """
    a = row[_SOM_PAD + "_start"] - max_distance
    b = row[_SOM_PAD + "_end"] - max_distance
    seg_len = row[_SEG_LEN]
    min_norm_path_distances, max_norm_path_distances = find_normalized_interval_below_zero(a, b)

    return pd.Series(
        {_SEG_MIN: min_norm_path_distances * seg_len, _SEG_MAX: max_norm_path_distances * seg_len}
    )


def min_max_offset_for_center_segment(row: pd.Series, max_distance: float) -> pd.Series:
    """Determines offsets from segment starting point closer than max_distance. \

    Determines which offsets from the starting point of a segment are closer in path distance \
        than a specified maximum value. Specialized version to be used for the segment that \
        contains the point that path distances are relative to.

    Args:
        row (pd.Series): Must specify path distance at the start and end of the segment,
        plus the length of the segment. For the names of the corresponding entries check the code.
        max_distance (float): Maximum path distance allowed.
    """
    a = row[_SOM_PAD + "_start"] - max_distance
    b = row[_SOM_PAD + "_end"] - max_distance
    seg_len = row[_SEG_LEN]
    c = -max_distance
    min_norm_path_distances, _ = find_normalized_interval_below_zero(a, c)
    _, max_norm_path_distances = find_normalized_interval_below_zero(c, b)

    return pd.Series(
        {
            _SEG_MIN: 0.5 * min_norm_path_distances * seg_len,
            _SEG_MAX: (0.5 + 0.5 * max_norm_path_distances) * seg_len,
        }
    )


def candidate_segments_all_morphology(locs: pandas.DataFrame) -> pd.DataFrame:
    """Creates a dataframe matching the format of 'candidate_segments_for_center' (*).

    * But where all parts of the morphology are admitted as candidates. \
            For details, see that function.
    """
    return pd.DataFrame(
        {_SEG_MIN: np.zeros(len(locs), dtype=float), _SEG_MAX: locs[_SEG_LEN].to_numpy()},
        index=locs.index,
    )


def candidate_segments_for_center(
    ids_center: list,
    locs: pd.DataFrame,
    max_dist: float,
    m: morphio.Morphology,
    path_distance_calculator: MorphologyPathDistanceCalculator,
    lst_sec_types: list | None = None,
) -> pd.DataFrame:
    """Creates dataframe specifying candidate locations to be picked around center of a cluster.

    That is, finds for all segments intervals that are closer than a maximum distance to the \
        center. If no part of a segment is closer than the value, then the segment is omitted \
            from the output.

    Output is a DataFrame with one row per candidate segment. Columns specify the minimum and \
        maximum within-segment offset in um that is still within the maximum distance.

    Args:
        ids_center (list): List of integers that can be used as index into 'locs'. Specifies the \
            locations of the centers picked.
        locs (pd.DataFrame): dataframe of section id, segment id, soma path distance of all \
            segments
        max_dist (float): Maximum distance from the center allowed
        m (morphio.morphology): morphology to use
        path_distance_calculator (conntility.subcellular.MorphologyPathDistanceCalculator): must \
            be defined on 'm'
        lst_sec_types (list, default=None): List of section types allowed. If None, then all \
            types are allowed.
    """
    loc_center = locs.loc[ids_center]
    res_seg_start = path_distance_all_segments_from(
        loc_center, m, path_distance_calculator, 0.0, lst_sec_types=lst_sec_types
    ).rename(columns={_SOM_PAD: _SOM_PAD + "_start"})
    res_seg_end = path_distance_all_segments_from(
        loc_center, m, path_distance_calculator, 1.0, lst_sec_types=lst_sec_types
    ).rename(columns={_SOM_PAD: _SOM_PAD + "_end"})

    res = pd.concat([res_seg_start, res_seg_end[[_SOM_PAD + "_end"]]], axis=1)

    valid = (res[_SOM_PAD + "_start"] < max_dist) | (res[_SOM_PAD + "_end"] < max_dist)
    valid[list(enumerate(ids_center))] = True
    cands = res.loc[valid]

    intervals = cands.apply(min_max_offset_in_segment, args=(max_dist,), axis=1)
    for tpl in enumerate(ids_center):
        intervals.loc[tpl] = min_max_offset_for_center_segment(res.loc[tpl], max_dist)
    return intervals


def select_places_from_candidate_list(
    n: int, cands: pd.DataFrame, locs: pd.DataFrame
) -> pd.DataFrame:
    """From a list of candidate segments, pick randomly the specified number of locations.

    Locations are identified not just by their segment, but also the offset within the segment.
    Each candidate location is equally likely (no bias).

    Args:
        n (int): Number of locations to pick

        cands (pd.DataFrame): dataframe specifying segments and intervals on the segments that
        are valid to be picked. Output of 'candidate_segments_for_center'.

        locs (pd.DataFrame): dataframe of all segments on the morphology. Its index must be
        consistent with the index of 'cands'.
    """

    def randomly_pick_with_p(dataframe_in: pd.DataFrame) -> pd.DataFrame:
        dataframe_in = dataframe_in.droplevel(0)
        selected = dataframe_in.loc[
            np.random.choice(dataframe_in.index, n, p=dataframe_in["p"] / dataframe_in["p"].sum())  # noqa: NPY002
        ]
        selected = selected[_SEG_MIN] + np.random.rand(n) * (  # noqa: NPY002
            selected[_SEG_MAX] - selected[_SEG_MIN]
        )

        output = locs.loc[selected.index].sort_index().drop(columns=[_SEG_OFF])
        output[_SEG_OFF] = selected.to_numpy()
        return output

    p = cands.diff(axis=1).to_numpy()[:, 1]
    p[np.isnan(p)] = 0
    cands["p"] = p

    return cands.groupby(_CEN_IDX).apply(randomly_pick_with_p)


def map_presynaptic_ids(dataframe: pd.DataFrame, n_per_center: int) -> None:
    """Assign ids to generated locations.

    Locations around the same center are split into the specified number of groups and assigned \
        unique ids.

    Does not return an output, instead adds a column to the input dataframe.

    Args:
        dataframe (pd.DataFrame): Contains the selected locations. Defined by section id,
        segment id, segment offset, etc.

        n_per_center (int): Numner of unique identifiers per center.
    """
    rnd = np.random.randint(0, n_per_center, len(dataframe))  # noqa: NPY002
    dataframe[_PRE_IDX] = dataframe[_CEN_IDX] * n_per_center + rnd


def add_normalized_section_offset(
    dataframe: pd.DataFrame,
    m: morphio.Morphology,
    path_distance_calculator: MorphologyPathDistanceCalculator,
) -> None:
    """Adds the normalized section offset to a dataframe that defines morphology locations.

    Args:
        dataframe (pd.DataFrame): Contains the selected locations. Defined by section id,
        segment id, segment offset, etc.

        m (morphio.Morphology): morphology used

        path_distance_calculator (conntility.subcellular.MorphologyPathDistanceCalculator): Must \
            be defined on m.
    """
    sec_lengths = np.array(
        [np.linalg.norm(np.diff(sec.points, axis=0), axis=1).sum() for sec in m.sections]
    )
    sec_o = path_distance_calculator.O[dataframe[_SEC_ID] - 1, dataframe[_SEG_ID]]
    sec_l = sec_lengths[dataframe[_SEC_ID] - 1]
    dataframe[_SEC_LOC] = sec_o / sec_l


def generate_neurite_locations_on(
    m: morphio.Morphology,
    n_centers: int,
    n_per_center: int,
    srcs_per_center: int,
    center_path_distances_mean: float,
    center_path_distances_sd: float,
    max_dist_from_center: float,
    lst_section_types: list | None = None,
    seed: float | None = None,
) -> pd.DataFrame:
    """Generates a specified number of morphology locations according to complex specifications.

    Locations are defined along morphology skeleton, i.e. they are 1d locations, not membrane \
        locations.

    Locations are 'clustered' around center locations on the morphology. If that is not required, \
        the parameter 'max_dist_from_center' can be set to None and clustering is ignored.

    Otherwise, the locations of the centers can be parameterized by specifying the mean and \
        standard deviation of a Gaussian. The probability that any given neurite location is \
        picked is then proportional to the value of the Gaussian at the path distance from \
        the soma of the location. Note that this is *not* equivalent to saying that the \
        distribution of path distances of the output locations follows the Gaussian. \
        This is because some path distances are more common than others on the input morphology.

    If you do not want to constrain path distances, simply set the standard deviation of the \
        Gaussian to a very high value and then all morphology locations are equally likely.

    Output is a pd.DataFrame with one row per location. Columns define:
      - segment id
      - section id
      - section type
      - segment offset
      - soma path distance
      - normalized section offset
      - center id
      - source id

    where "center id" is an identifier for the center that a location is associated with. Even if
    'max_dist_from_center' is set to None, center ids are still generated.

    "source id" is defining a conceptual grouping that is generated according to specifications.\
        For example, when using this function to generate a synaptome, this could be the \
        presynaptic neuron id.

    Args:
        m (morphio.Morphology): The morphology to use.

        n_centers (int): Number of centers to group locations around. If not needed, set to 1.

        n_per_center (int): Number of locations to generate for each center.

        srcs_per_center (int): Number of source ids per center. Used to generate the source id.
        If not needed, set to 1.

        center_path_distances_mean (float): Mean of the Gaussian determining center path distances

        center_path_distances_sd (float): Standard deviation of the same Gaussian. If path \
            distances are no concern, then set this to 1E20 or a similarly large number

        max_dist_from_center (float): Maximum path distance from the center for the generated\
            locations.

        lst_section_types (list, default=None): List of section types that are valid targets. If \
            None, all types are valid.

        seed (optional): Random seed. For reproducability.
    """
    if seed is not None:
        np.random.seed(seed)  # noqa: NPY002

    path_distance_calculator = MorphologyPathDistanceCalculator(m)

    soma = pd.DataFrame({_SEC_ID: [0], _SEG_ID: [0], _SEG_OFF: [0]})

    locs = path_distance_all_segments_from(
        soma, m, path_distance_calculator, lst_sec_types=lst_section_types
    ).loc[0]

    if (
        max_dist_from_center is None
    ):  # Simpler case. If clustering around a center is not a concern.
        cands_all_morph = candidate_segments_all_morphology(locs)
        lst_candidates_per_center = pd.concat(
            [cands_all_morph for _ in range(n_centers)],
            axis=0,
            keys=range(n_centers),
            names=[_CEN_IDX],
        )
    else:
        distr = stats.norm(center_path_distances_mean, center_path_distances_sd)
        centers = select_segments_as_cluster_centers(n_centers, locs, distr, lst_sec_types=None)
        lst_candidates_per_center = candidate_segments_for_center(
            centers.index,
            locs,
            max_dist_from_center,
            m,
            path_distance_calculator,
            lst_sec_types=lst_section_types,
        )

    all_clusters = select_places_from_candidate_list(n_per_center, lst_candidates_per_center, locs)

    # Which columns do you want in the output?
    relevant_cols = [_SEG_ID, _SEC_ID, _SEC_TYP, _SEG_OFF, _SOM_PAD]
    all_clusters = all_clusters.droplevel(1)[relevant_cols].reset_index()

    map_presynaptic_ids(all_clusters, srcs_per_center)
    add_normalized_section_offset(all_clusters, m, path_distance_calculator)
    return all_clusters
