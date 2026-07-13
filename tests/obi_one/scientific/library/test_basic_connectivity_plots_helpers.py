"""Tests for basic_connectivity_plots_helpers connectivity computations."""

import numpy as np
import pytest
from connalysis.network.classic import connection_probability_within
from connalysis.network.topology import node_degree, rc_submatrix
from conntility import ConnectivityMatrix

from obi_one.scientific.library.basic_connectivity_plots_helpers import (
    connection_probability_within_pathway,
    directed_connection_probability_within,
    in_out_degree,
)

from tests.utils import MATRIX_DIR

MATRIX_NAMES = ["N_10__top_nodes_dim6", "N_10__top_rc_nodes_dim2_rc"]


def _load_conn(name):
    return ConnectivityMatrix.from_h5(str(MATRIX_DIR / name / "connectivity_matrix.h5"))


def _load_matrix(name):
    conn = _load_conn(name)
    return conn.matrix.astype(bool).tocsc(), conn.vertices


def _pathway_within_via_connalysis(conn, grouping_prop, max_dist):
    """Reference pathway probabilities using connalysis as the analysis source."""
    specs = {
        "analyses": {
            "probability_within": {
                "source": connection_probability_within,
                "args": [["x", "y", "z"], max_dist, "directed"],
                "output": "scalar",
                "decorators": [
                    {
                        "name": "pathways_by_grouping_config",
                        "args": [{"columns": [grouping_prop], "method": "group_by_properties"}],
                    }
                ],
            }
        }
    }
    out = conn.analyze(specs)
    return out["probability_within"].unstack(f"idx-{grouping_prop}_post")


def _assert_equal_with_nan(actual, expected):
    if np.isnan(expected):
        assert np.isnan(actual)
    else:
        assert actual == pytest.approx(expected, rel=1e-9, abs=1e-12)


class TestDirectedConnectionProbabilityWithin:
    """The edge-based helper must reproduce connalysis but scale to large circuits."""

    @pytest.mark.parametrize("matrix_name", MATRIX_NAMES)
    @pytest.mark.parametrize("cols", [["x", "y"], ["x", "y", "z"]])
    @pytest.mark.parametrize("max_dist", [100, 300, 1000])
    def test_matches_connalysis_single_population(self, matrix_name, cols, max_dist):
        # Counting over edges must give the same probability as connalysis, which
        # materialises the full within-distance pair mask (only feasible for small
        # circuits) and indexes the adjacency matrix with it.
        m, v = _load_matrix(matrix_name)
        for mat in (m, rc_submatrix(m)):
            expected = connection_probability_within(
                mat, v, cols=cols, max_dist=max_dist, type="directed", skip_symmetry_check=True
            )
            actual = directed_connection_probability_within(mat, v, max_dist=max_dist, cols=cols)
            assert actual == pytest.approx(expected, rel=1e-9, abs=1e-12)

    @pytest.mark.parametrize("matrix_name", MATRIX_NAMES)
    @pytest.mark.parametrize("max_dist", [300, 1000])
    def test_matches_connalysis_cross_population(self, matrix_name, max_dist):
        # Pathways pass distinct pre/post populations as a (vpre, vpost) tuple and a
        # non-square submatrix; connalysis skips its diagonal removal in that case.
        m, v = _load_matrix(matrix_name)
        cols = ["x", "y", "z"]
        pre_idx, post_idx = np.arange(0, m.shape[0], 2), np.arange(1, m.shape[0], 2)
        subm = m[np.ix_(pre_idx, post_idx)]
        vv = (v.iloc[pre_idx], v.iloc[post_idx])
        expected = connection_probability_within(
            subm, vv, cols=cols, max_dist=max_dist, type="directed", skip_symmetry_check=True
        )
        actual = directed_connection_probability_within(subm, vv, max_dist=max_dist, cols=cols)
        _assert_equal_with_nan(actual, expected)

    def test_returns_nan_when_no_pairs_within_distance(self):
        # With a tiny max_dist no two distinct nodes are within range. connalysis
        # divides by zero here; the helper must instead degrade gracefully to nan.
        m, v = _load_matrix("N_10__top_nodes_dim6")
        result = directed_connection_probability_within(m, v, max_dist=1e-9, cols=["x", "y"])
        assert np.isnan(result)


class TestInOutDegree:
    """Sparse in/out degree must match connalysis without densifying the matrix."""

    @pytest.mark.parametrize("matrix_name", MATRIX_NAMES)
    def test_matches_node_degree(self, matrix_name):
        m, _ = _load_matrix(matrix_name)
        for adj in (m, rc_submatrix(m)):
            expected = node_degree(adj, direction=("IN", "OUT"))
            actual = in_out_degree(adj)
            assert list(actual.columns) == ["IN", "OUT"]
            assert np.array_equal(actual["IN"].to_numpy(), expected["IN"].to_numpy())
            assert np.array_equal(actual["OUT"].to_numpy(), expected["OUT"].to_numpy())


class TestConnectionProbabilityWithinPathway:
    """The wired pathway computation must match connalysis pathway-for-pathway."""

    @pytest.mark.parametrize(
        ("matrix_name", "grouping_prop"),
        [
            ("N_10__top_nodes_dim6", "synapse_class"),
            ("N_10__top_nodes_dim6", "mtype"),
            ("N_10__top_rc_nodes_dim2_rc", "mtype"),
        ],
    )
    @pytest.mark.parametrize("max_dist", [100, 1000])
    def test_matches_connalysis(self, matrix_name, grouping_prop, max_dist):
        conn = _load_conn(matrix_name)
        expected = _pathway_within_via_connalysis(conn, grouping_prop, max_dist)
        actual = connection_probability_within_pathway(conn, grouping_prop, max_dist=max_dist)
        # Identical pathway grid (pre x post groups) and equal values, nan for nan.
        assert list(actual.index) == list(expected.index)
        assert list(actual.columns) == list(expected.columns)
        both_nan = expected.isna() & actual.isna()
        assert ((expected == actual) | both_nan).to_numpy().all()
