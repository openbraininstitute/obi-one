"""Tests for basic_connectivity_plots_helpers connectivity computations."""

import matplotlib as mpl
import numpy as np
import pytest
from connalysis.network.classic import connection_probability_within
from connalysis.network.topology import node_degree, rc_submatrix
from conntility import ConnectivityMatrix

mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Wedge

from obi_one.scientific.library.basic_connectivity_plots_helpers import (
    CANONICAL_EXC,
    CANONICAL_INH,
    CANONICAL_NA,
    CANONICAL_NA_COLOR,
    assemble_property_colormapping,
    connection_probability_within_pathway,
    directed_connection_probability_within,
    in_out_degree,
    make_pie_plot,
    map_canonical_synapse_classes,
    plot_smallMC,
)

from tests.utils import MATRIX_DIR

MATRIX_NAMES = ["N_10__top_nodes_dim6", "N_10__top_rc_nodes_dim2_rc"]


def _load_conn(name):
    return ConnectivityMatrix.from_h5(str(MATRIX_DIR / name / "connectivity_matrix.h5"))


def _conn_with_na_value(name, prop, match_value):
    """Return a copy of a connectome with one node's `prop` relabelled to "N/A".

    No shipped example matrix carries N/A values, so inject one onto a node that
    currently has `match_value`, leaving the remaining values intact.
    """
    conn = _load_conn(name)
    vertices = conn.vertices.copy()
    values = vertices[prop].astype(str).to_numpy().copy()
    positions = np.where(values == match_value)[0]
    values[positions[0]] = "N/A"
    vertices[prop] = values
    return ConnectivityMatrix(
        conn.matrix,
        vertex_properties=vertices,
        edge_properties=conn.edges,
        default_edge_property="data",
    )


def _conn_with_na_class(name):
    """Return a copy of a connectome with one EXC node relabelled to synapse_class "N/A"."""
    return _conn_with_na_value(name, "synapse_class", "EXC")


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


def _synapse_class_legend_labels(fig):
    """Collect the synapse-class marker labels drawn across a figure's axes."""
    return [
        txt.get_text() for ax in fig.axes for txt in ax.texts if txt.get_text() in {"EXC", "INH"}
    ]


def _visible_empty_axes(fig):
    """Axes left framed/visible but carrying no drawn content."""
    return [
        i
        for i, ax in enumerate(fig.axes)
        if ax.axison and not (ax.texts or ax.images or ax.patches or ax.lines or ax.collections)
    ]


class TestPlotSmallMCLegend:
    """plot_smallMC must draw one node legend per present synapse class.

    Regression guard: with a single synapse class the function used to leave an
    empty, still-visible legend axis where the second class marker would normally
    go. The node legend must show exactly the classes present, and no legend axis
    may be left framed with nothing drawn in it.
    """

    @pytest.mark.parametrize(
        ("matrix_name", "expected_labels"),
        [
            ("N_10__top_rc_nodes_dim2_rc", ["EXC"]),
            ("N_10__top_nodes_dim6", ["EXC", "INH"]),
        ],
    )
    def test_node_legend_matches_synapse_classes(self, matrix_name, expected_labels):
        conn = _load_conn(matrix_name)
        present = sorted(conn.vertices["synapse_class"].unique())
        assert present == expected_labels, "matrix fixture no longer has expected classes"

        fig = plot_smallMC(conn, plt.get_cmap("viridis"), full_width=10)
        try:
            assert sorted(_synapse_class_legend_labels(fig)) == expected_labels
            # The single-class bug surfaced as a framed-but-empty legend axis.
            assert _visible_empty_axes(fig) == []
        finally:
            plt.close(fig)


class TestAssemblePropertyColormapping:
    """Synapse-class colours must be anchored to canonical ends of the colormap.

    Regression guard: a single-class (e.g. EXC-only) circuit used to colour its one
    class from index 0 of the colormap (the INH/cool end), so EXC rendered blue
    instead of red. EXC must always take the warm end and INH the cool end,
    independent of how many classes are present.
    """

    # The real plots build colours from this blue (INH) -> red (EXC) colormap.
    CMAP = LinearSegmentedColormap.from_list("RedBlue", ["C0", "C3"])

    def _cool_warm(self):
        return self.CMAP(0), self.CMAP(self.CMAP.N)

    def test_single_exc_class_uses_warm_end(self):
        cool, warm = self._cool_warm()
        conn = _load_conn("N_10__top_rc_nodes_dim2_rc")
        assert sorted(conn.vertices["synapse_class"].unique()) == ["EXC"]

        color_map = assemble_property_colormapping(conn, self.CMAP)

        assert color_map["EXC"] == warm
        assert color_map["EXC"] != cool

    def test_two_classes_anchor_exc_warm_inh_cool(self):
        cool, warm = self._cool_warm()
        conn = _load_conn("N_10__top_nodes_dim6")
        assert sorted(conn.vertices["synapse_class"].unique()) == ["EXC", "INH"]

        color_map = assemble_property_colormapping(conn, self.CMAP)

        assert color_map["EXC"] == warm
        assert color_map["INH"] == cool

    def test_exc_colour_consistent_across_circuits(self):
        single = assemble_property_colormapping(_load_conn("N_10__top_rc_nodes_dim2_rc"), self.CMAP)
        dual = assemble_property_colormapping(_load_conn("N_10__top_nodes_dim6"), self.CMAP)
        # EXC must look identical whether or not INH is also present.
        assert single["EXC"] == dual["EXC"]

    def test_na_class_is_grey_not_a_colormap_colour(self):
        cool, warm = self._cool_warm()
        conn = _conn_with_na_class("N_10__top_nodes_dim6")
        assert sorted(conn.vertices["synapse_class"].unique()) == ["EXC", "INH", "N/A"]

        color_map = assemble_property_colormapping(conn, self.CMAP)

        # N/A is always the fixed grey, never sampled from the colormap.
        assert color_map["N/A"] == CANONICAL_NA_COLOR
        assert color_map["N/A"] not in {cool, warm}
        # E/I colours are unaffected by the presence of an N/A class.
        assert color_map["EXC"] == warm
        assert color_map["INH"] == cool

    def test_na_is_grey_for_generic_property(self):
        # The grey-for-N/A rule applies to any grouping property, not just
        # synapse_class. Here a layer value is relabelled N/A.
        conn = _conn_with_na_value("N_10__top_nodes_dim6", "layer", "3")
        layers = conn.vertices["layer"].astype(str)
        assert "N/A" in set(layers.unique())

        color_map = assemble_property_colormapping(conn, self.CMAP, color_property="layer")

        assert color_map["N/A"] == CANONICAL_NA_COLOR
        # Remaining real layers still receive distinct colormap colours.
        real_colors = [c for val, c in color_map.items() if val != "N/A"]
        assert all(c != CANONICAL_NA_COLOR for c in real_colors)


class TestMapCanonicalSynapseClasses:
    """Canonical classification must recognise EXC/INH and treat the rest as N/A.

    Real circuits carry literal "N/A" values for synapse_class or layer, so these
    must map to the canonical N/A slot rather than being dropped or mislabelled.
    """

    def test_na_literal_maps_to_canonical_na(self):
        mapping = map_canonical_synapse_classes(["EXC", "INH", "N/A"])
        assert mapping == {"EXC": CANONICAL_EXC, "INH": CANONICAL_INH, "N/A": CANONICAL_NA}

    def test_single_na_slot_only(self):
        # Only the first non-E/I value takes the N/A slot; extras are not mapped.
        mapping = map_canonical_synapse_classes(["N/A", "other"])
        assert mapping == {"N/A": CANONICAL_NA}

    def test_substring_matches_are_case_insensitive(self):
        mapping = map_canonical_synapse_classes(["excitatory", "Inhibitory"])
        assert mapping == {"excitatory": CANONICAL_EXC, "Inhibitory": CANONICAL_INH}


class TestMakePiePlotNaColour:
    """Pie charts must draw N/A groups grey for any grouping property.

    The layer/mtype pie slices sample the colormap directly (they do not go through
    assemble_property_colormapping), so N/A handling must be enforced there too.
    """

    def _wedge_colours(self, ax):
        return [tuple(wedge.get_facecolor()) for wedge in ax.patches]

    def test_layer_na_slice_is_grey(self):
        cmaps = {
            "synapse_class": LinearSegmentedColormap.from_list("RedBlue", ["C0", "C3"]),
            "layer": plt.get_cmap("Dark2"),
            "mtype": plt.get_cmap("GnBu"),
        }
        conn = _conn_with_na_value("N_10__top_nodes_dim6", "layer", "3")
        fig, ax = plt.subplots()
        try:
            make_pie_plot(ax, conn, "layer", cmaps)
            grey = tuple(CANONICAL_NA_COLOR)
            colours = self._wedge_colours(ax)
            # Exactly one slice (the N/A layer) is grey; the rest are colormap colours.
            assert colours.count(grey) == 1
            assert any(c != grey for c in colours)
        finally:
            plt.close(fig)

    def test_na_does_not_consume_a_colormap_index(self):
        # The N/A group must not take a colour slot: with n_real real groups, only
        # colormap indices 0..n_real-1 may be used. Dark2's trailing index (7) is a
        # dark grey, so if N/A consumed a slot a real group would wrongly get it.
        n_real = 7  # 7 real layers + N/A exercises Dark2's grey index 7
        conn = _load_conn("N_10__top_nodes_dim6")
        vertices = conn.vertices.copy()
        labels = [str(i) for i in range(n_real)] + ["N/A"]
        node_count = len(vertices)
        vertices["layer"] = [labels[i % len(labels)] for i in range(node_count)]
        conn = ConnectivityMatrix(
            conn.matrix,
            vertex_properties=vertices,
            edge_properties=conn.edges,
            default_edge_property="data",
        )

        cmap = plt.get_cmap("Dark2")
        fig, ax = plt.subplots()
        try:
            make_pie_plot(ax, conn, "layer", {"layer": cmap})
            colours = self._wedge_colours(ax)
            real_colours = [c for c in colours if c != tuple(CANONICAL_NA_COLOR)]
            allowed = {tuple(cmap(i)) for i in range(n_real)}
            assert set(real_colours) == allowed
            assert tuple(cmap(n_real)) not in set(real_colours)
        finally:
            plt.close(fig)

    def test_slices_are_sorted_alphabetically_by_label(self):
        # value_counts returns categories in count order; make_pie_plot must reorder
        # them alphabetically by label so e.g. layers read 1, 2, 3, ... not by size.
        conn = _load_conn("N_10__top_nodes_dim6")
        vertices = conn.vertices.copy()
        node_count = len(vertices)
        # Assign layers so the count order differs from the alphabetical order.
        layer_sequence = ["3", "3", "3", "3", "1", "1", "1", "2", "2", "6"]
        vertices["layer"] = [layer_sequence[i % len(layer_sequence)] for i in range(node_count)]
        conn = ConnectivityMatrix(
            conn.matrix,
            vertex_properties=vertices,
            edge_properties=conn.edges,
            default_edge_property="data",
        )

        fig, ax = plt.subplots()
        try:
            make_pie_plot(ax, conn, "layer", {"layer": plt.get_cmap("Dark2")})
            labels = [t.get_text().split(":")[0] for t in ax.texts if t.get_text()]
            assert labels == sorted(labels)
            assert labels == ["1", "2", "3", "6"]
        finally:
            plt.close(fig)

    def test_slices_are_drawn_clockwise(self):
        # Sorted categories should run clockwise, i.e. each successive wedge midpoint
        # angle is smaller than the previous one (angles decrease going clockwise).
        conn = _load_conn("N_10__top_nodes_dim6")
        vertices = conn.vertices.copy()
        node_count = len(vertices)
        layer_sequence = ["3", "3", "3", "3", "1", "1", "1", "2", "2", "6"]
        vertices["layer"] = [layer_sequence[i % len(layer_sequence)] for i in range(node_count)]
        conn = ConnectivityMatrix(
            conn.matrix,
            vertex_properties=vertices,
            edge_properties=conn.edges,
            default_edge_property="data",
        )

        fig, ax = plt.subplots()
        try:
            make_pie_plot(ax, conn, "layer", {"layer": plt.get_cmap("Dark2")})
            wedges = [w for w in ax.patches if isinstance(w, Wedge)]
            midpoints = [(w.theta1 + w.theta2) / 2 for w in wedges]
            assert midpoints == sorted(midpoints, reverse=True)
        finally:
            plt.close(fig)
