"""Regression tests pinning the segment table built by ``path_distance_all_segments_from``.

The function builds one row per morphology segment. It is shared by morphology-location
generation, Build Synaptome, and EM synapse mapping, so its output (row count, ordering,
section/segment labelling, section types, and dtypes) must stay stable. These tests pin that
structure against a real morphology, independent of the internal implementation, so a future
rewrite that changes the table is caught here.
"""

import morphio
import numpy as np
import pandas as pd
import pytest
from conntility.subcellular import OptimizedMorphologyPathDistanceCalculator

import obi_one.scientific.library.morphology_locations as morphology_locations_module
from obi_one.scientific.library.morphology_locations import (
    _SEC_ID,
    _SEC_TYP,
    _SEG_ID,
    _SEG_LEN,
    _SEG_MAX,
    _SEG_MIN,
    _SOM_PAD,
    candidate_segments_for_center,
    find_normalized_interval_below_zero,
    min_max_offsets_in_segments,
    path_distance_all_segments_from,
)

from tests.utils import DATA_DIR


def _soma_ref() -> pd.DataFrame:
    return pd.DataFrame({_SEC_ID: [0], _SEG_ID: [0], "segment_offset": [0.0]})


@pytest.fixture
def morphology():
    return morphio.Morphology(DATA_DIR / "cell_morphology.swc", options=morphio.Option.nrn_order)


def test_segment_table_matches_morphology_structure(morphology):
    """Each section contributes exactly ``n_points - 1`` rows, in section order."""
    result = path_distance_all_segments_from(
        _soma_ref(), morphology, OptimizedMorphologyPathDistanceCalculator(morphology)
    ).loc[0]

    sections = list(morphology.sections)
    expected_seg_id = np.concatenate([np.arange(s.n_points - 1) for s in sections])
    expected_sec_id = np.repeat(np.arange(1, len(sections) + 1), [s.n_points - 1 for s in sections])
    expected_sec_typ = np.repeat(
        [int(s.type) for s in sections], [s.n_points - 1 for s in sections]
    )

    assert len(result) == sum(s.n_points - 1 for s in sections)
    np.testing.assert_array_equal(result[_SEG_ID].to_numpy(), expected_seg_id)
    np.testing.assert_array_equal(result[_SEC_ID].to_numpy(), expected_sec_id)
    np.testing.assert_array_equal(result[_SEC_TYP].to_numpy(), expected_sec_typ)


def test_segment_table_dtypes_are_stable(morphology):
    """Downstream merges rely on integer ids/types and float lengths."""
    result = path_distance_all_segments_from(
        _soma_ref(), morphology, OptimizedMorphologyPathDistanceCalculator(morphology)
    ).loc[0]

    assert result[_SEG_ID].dtype == np.dtype("int64")
    assert result[_SEC_ID].dtype == np.dtype("int64")
    assert result[_SEC_TYP].dtype == np.dtype("int64")
    # Segment length is floating; its precision follows the morphology's point precision
    # (float32 for this SWC fixture), so assert the kind rather than a fixed width.
    assert np.issubdtype(result[_SEG_LEN].dtype, np.floating)


def test_section_type_filter_keeps_only_requested_types(morphology):
    """Filtering by section type drops every row of other types, nothing else."""
    present = sorted(int(s.type) for s in morphology.sections)
    kept_type = present[0]

    result = path_distance_all_segments_from(
        _soma_ref(),
        morphology,
        OptimizedMorphologyPathDistanceCalculator(morphology),
        lst_sec_types=[kept_type],
    ).loc[0]

    assert set(result[_SEC_TYP].unique()) == {kept_type}


def test_no_matching_section_types_raises(morphology):
    """A filter that matches no segment is an explicit error, not an empty frame."""
    with pytest.raises(ValueError, match="No morphology segments match"):
        path_distance_all_segments_from(
            _soma_ref(),
            morphology,
            OptimizedMorphologyPathDistanceCalculator(morphology),
            lst_sec_types=[999],
        )


def test_min_max_offsets_in_segments_match_the_scalar_interval():
    """The vectorized offsets equal ``find_normalized_interval_below_zero`` row by row."""
    rng = np.random.default_rng(0)
    max_distance = 150.0
    start = rng.uniform(0.0, 300.0, 2000)
    end = start + rng.uniform(-40.0, 40.0, 2000)
    end[:50] = start[:50]  # segments with equal start and end distance
    in_range = np.minimum(start, end) < max_distance
    cands = pd.DataFrame(
        {
            _SOM_PAD + "_start": start,
            _SOM_PAD + "_end": end,
            _SEG_LEN: rng.uniform(1.0, 40.0, 2000),
        }
    )[in_range]
    result = min_max_offsets_in_segments(cands, max_distance)
    expected = [
        tuple(
            bound * length
            for bound in find_normalized_interval_below_zero(s - max_distance, e - max_distance)
        )
        for s, e, length in zip(
            cands[_SOM_PAD + "_start"], cands[_SOM_PAD + "_end"], cands[_SEG_LEN], strict=True
        )
    ]
    assert len(result) > 1000
    np.testing.assert_allclose(result[[_SEG_MIN, _SEG_MAX]].to_numpy(), expected)


def test_candidate_segments_do_not_depend_on_the_center_batch_size(morphology, monkeypatch):
    """Processing centers in several batches gives the same candidates as in one."""
    calculator = OptimizedMorphologyPathDistanceCalculator(morphology)
    segments = path_distance_all_segments_from(
        _soma_ref(), morphology, calculator, lst_sec_types=[3, 4]
    ).loc[0]
    args = (list(segments.index[::7][:8]), segments, 50.0, morphology, calculator, [3, 4])
    expected = candidate_segments_for_center(*args)
    monkeypatch.setattr(morphology_locations_module, "_CENTER_BATCH_SIZE", 3)
    pd.testing.assert_frame_equal(candidate_segments_for_center(*args), expected)
