"""Unit tests for the pure selection/filter helpers in find_afferent_synapses.

These cover the filtering, random selection, path-distance boundary selection, and
synapse-merging logic with small in-memory DataFrames. The morphology/path-distance
dependent functions (which require the optional ``conntility`` package) are not
exercised here; only the dependency-free data-manipulation core is tested.
"""

import numpy as np
import pandas as pd
import pytest

from obi_one.scientific.library.find_afferent_synapses import (
    apply_filters,
    merge_multiple_syns_per_connection,
    select_minmax_distance,
    select_randomly,
)


@pytest.fixture
def section_type_syns():
    return pd.DataFrame({"afferent_section_type": [1, 2, 3, 2], "value": [10, 20, 30, 40]})


@pytest.fixture
def value_range_syns():
    return pd.DataFrame({"value": range(10)})


def test_apply_filters_scalar_keeps_matching_rows(section_type_syns):
    result = apply_filters(section_type_syns, {"afferent_section_type": 2})
    assert list(result["value"]) == [20, 40]


def test_apply_filters_list_keeps_rows_in_set():
    syns = pd.DataFrame({"afferent_section_type": [1, 2, 3, 4], "value": [10, 20, 30, 40]})
    result = apply_filters(syns, {"afferent_section_type": [1, 3]})
    assert list(result["value"]) == [10, 30]


def test_apply_filters_multiple_are_anded():
    syns = pd.DataFrame({"a": [1, 1, 2, 2], "b": ["x", "y", "x", "y"], "value": [1, 2, 3, 4]})
    result = apply_filters(syns, {"a": 1, "b": "y"})
    assert list(result["value"]) == [2]


def test_apply_filters_missing_column_raises():
    syns = pd.DataFrame({"a": [1, 2]})
    with pytest.raises(ValueError, match="No property not_there could be loaded"):
        apply_filters(syns, {"not_there": 1})


def test_apply_filters_drop_nan_true_drops_nan_rows():
    syns = pd.DataFrame({"a": [1.0, np.nan, 1.0], "value": [10, 20, 30]})
    result = apply_filters(syns, {"a": 1.0}, drop_nan=True)
    assert list(result["value"]) == [10, 30]


def test_apply_filters_drop_nan_false_keeps_nan_rows():
    syns = pd.DataFrame({"a": [1.0, np.nan, 2.0], "value": [10, 20, 30]})
    result = apply_filters(syns, {"a": 1.0}, drop_nan=False)
    # The matching row (10) and the nan row (20) pass; the 2.0 row (30) is dropped.
    assert list(result["value"]) == [10, 20]


def test_select_randomly_n_returns_exactly_n_rows(value_range_syns):
    result = select_randomly(value_range_syns, n=3)
    assert len(result) == 3


def test_select_randomly_n_larger_than_population_returns_all():
    syns = pd.DataFrame({"value": range(4)})
    result = select_randomly(syns, n=10)
    assert len(result) == 4


def test_select_randomly_n_larger_than_population_raises_when_requested():
    syns = pd.DataFrame({"value": range(4)})
    with pytest.raises(RuntimeError, match="Fewer than the requested count of 10 found"):
        select_randomly(syns, n=10, raise_insufficient=True)


def test_select_randomly_probability_one_keeps_all():
    syns = pd.DataFrame({"value": range(5)})
    result = select_randomly(syns, p=1.0)
    assert len(result) == 5


def test_select_randomly_probability_zero_keeps_none():
    syns = pd.DataFrame({"value": range(5)})
    result = select_randomly(syns, p=0.0)
    assert len(result) == 0


def test_select_randomly_probability_out_of_range_raises():
    syns = pd.DataFrame({"value": range(5)})
    with pytest.raises(ValueError, match="must be between 0 and 1"):
        select_randomly(syns, p=1.5)


def test_select_randomly_no_count_or_fraction_raises():
    syns = pd.DataFrame({"value": range(5)})
    with pytest.raises(ValueError, match="Must specify number or fraction"):
        select_randomly(syns)


def test_select_minmax_distance_restricts_to_interval():
    syns = pd.DataFrame({"value": [0, 1, 2, 3, 4]})
    soma_pds = np.array([5.0, 15.0, 25.0, 35.0, 45.0])
    # Interval [10, 40): rows at 15, 25, 35 -> values 1, 2, 3.
    result = select_minmax_distance(syns, soma_pds, soma_pd_min=10.0, soma_pd_max=40.0, p=1.0)
    assert sorted(result["value"]) == [1, 2, 3]


def test_select_minmax_distance_upper_bound_is_exclusive():
    syns = pd.DataFrame({"value": [0, 1]})
    soma_pds = np.array([10.0, 40.0])
    result = select_minmax_distance(syns, soma_pds, soma_pd_min=10.0, soma_pd_max=40.0, p=1.0)
    # 10.0 included (>= min), 40.0 excluded (< max).
    assert list(result["value"]) == [0]


def test_select_minmax_distance_insufficient_within_interval_raises():
    syns = pd.DataFrame({"value": [0, 1, 2]})
    soma_pds = np.array([5.0, 15.0, 100.0])
    with pytest.raises(RuntimeError, match="Fewer than the requested count"):
        select_minmax_distance(
            syns,
            soma_pds,
            soma_pd_min=10.0,
            soma_pd_max=40.0,
            n=3,
            raise_insufficient=True,
        )


def test_merge_multiple_syns_per_connection_averages_distances():
    # Two connections: (popA, 0) has two synapses (rows 0,1); (popA, 1) has one (row 2).
    syns = pd.DataFrame(
        {
            "source_population": ["popA", "popA", "popA"],
            "@source_node": [0, 0, 1],
        }
    )
    soma_pds = np.array([10.0, 20.0, 30.0])
    pw_pds = np.array(
        [
            [0.0, 2.0, 4.0],
            [2.0, 0.0, 6.0],
            [4.0, 6.0, 0.0],
        ]
    )

    syns_out, mn_soma_pd, mn_pw_pds = merge_multiple_syns_per_connection(syns, soma_pds, pw_pds)

    # One row per unique (source_population, @source_node) connection.
    assert len(syns_out) == 2
    assert set(syns_out["source_population"]) == {"popA"}
    assert sorted(syns_out["@source_node"]) == [0, 1]

    # Connection (popA, 0): mean soma pd of rows 0,1 = (10+20)/2 = 15.
    # Connection (popA, 1): mean soma pd of row 2 = 30.
    assert sorted(mn_soma_pd.tolist()) == [15.0, 30.0]

    # Pairwise matrix is square over the two merged connections.
    assert mn_pw_pds.shape == (2, 2)
