"""Tests for basic_connectivity_plots_helpers connectivity computations."""

import numpy as np
import pytest
from connalysis.network.classic import connection_probability_within
from connalysis.network.topology import rc_submatrix
from conntility import ConnectivityMatrix

from obi_one.scientific.library.basic_connectivity_plots_helpers import (
    directed_connection_probability_within,
)

from tests.utils import MATRIX_DIR

MATRIX_NAMES = ["N_10__top_nodes_dim6", "N_10__top_rc_nodes_dim2_rc"]


def _load_matrix(name):
    conn = ConnectivityMatrix.from_h5(str(MATRIX_DIR / name / "connectivity_matrix.h5"))
    return conn.matrix.astype(bool).tocsc(), conn.vertices


class TestDirectedConnectionProbabilityWithin:
    """The edge-based helper must reproduce connalysis but scale to large circuits."""

    @pytest.mark.parametrize("matrix_name", MATRIX_NAMES)
    @pytest.mark.parametrize("cols", [["x", "y"], ["x", "y", "z"]])
    @pytest.mark.parametrize("max_dist", [100, 300, 1000])
    def test_matches_connalysis(self, matrix_name, cols, max_dist):
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

    def test_returns_nan_when_no_pairs_within_distance(self):
        # With a tiny max_dist no two distinct nodes are within range. connalysis
        # divides by zero here; the helper must instead degrade gracefully to nan.
        m, v = _load_matrix("N_10__top_nodes_dim6")
        result = directed_connection_probability_within(m, v, max_dist=1e-9, cols=["x", "y"])
        assert np.isnan(result)
