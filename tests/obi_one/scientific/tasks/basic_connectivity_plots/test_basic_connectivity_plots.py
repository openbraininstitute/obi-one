import matplotlib as mpl
import pytest

from obi_one.core.path import NamedPath
from obi_one.core.run_tasks import run_tasks_for_generated_scan
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.tasks.basic_connectivity_plots import (
    BasicConnectivityPlotsScanConfig,
    BasicConnectivityPlotsTask,
)

mpl.use("Agg")
import matplotlib.pyplot as plt
from conntility import ConnectivityMatrix

from tests.utils import DATA_DIR, MATRIX_DIR


def test_basic_connectivity_plots(tmp_path):
    # Set up connectivity plotting
    matrix_list = [
        NamedPath(
            name="N_10__top_nodes_dim6",
            path=str(MATRIX_DIR / "N_10__top_nodes_dim6" / "connectivity_matrix.h5"),
        ),
        NamedPath(
            name="N_10__top_rc_nodes_dim2_rc",
            path=str(MATRIX_DIR / "N_10__top_rc_nodes_dim2_rc" / "connectivity_matrix.h5"),
        ),
    ]

    plot_init = BasicConnectivityPlotsScanConfig.Initialize(
        matrix_path=matrix_list,
        plot_formats=("png", "pdf", "svg"),
        rendering_cmap="custom",
        rendering_color_file=str(DATA_DIR / "colors_tab10.csv"),
    )
    basic_connectivity_plots_form = BasicConnectivityPlotsScanConfig(initialize=plot_init)

    # Run plot generation
    grid_scan = GridScanGenerationTask(
        form=basic_connectivity_plots_form,
        output_root=tmp_path / "grid_scan",
        coordinate_directory_option="VALUE",
    )
    grid_scan.execute()
    run_tasks_for_generated_scan(grid_scan)

    # Check that expected files have been created
    instances = grid_scan.single_configs
    assert len(instances) == 2
    for instance in instances:
        out_path = tmp_path / grid_scan.output_root / instance.initialize.matrix_path.name
        assert (out_path / "size.npy").exists()
        for fmt in instance.initialize.plot_formats:
            assert (out_path / f"network_global_stats.{fmt}").exists()
            assert (out_path / f"network_pathway_stats.{fmt}").exists()
            assert (out_path / f"node_stats.{fmt}").exists()
            assert (out_path / f"property_table.{fmt}").exists()
            assert (out_path / f"small_adj_and_stats.{fmt}").exists()
            assert (out_path / f"small_network_in_2D.{fmt}").exists()


def _circular_overview_axes(conn, tmp_path, monkeypatch):
    """Run network_in_2D_circular_plot and capture the figure's axes before it is closed.

    Returns a list of (axison, has_content, legend_label_texts) per axis. The task saves
    and closes the figure internally, so plt.close is patched to snapshot it first.
    """
    captured = {}
    original_close = plt.close

    def spy_close(*args, **kwargs):
        fig = plt.gcf()
        captured["axes"] = [
            (
                ax.axison,
                bool(ax.texts or ax.images or ax.patches or ax.lines or ax.collections),
                [t.get_text() for t in ax.texts if t.get_text() in {"EXC", "INH"}],
            )
            for ax in fig.axes
        ]
        return original_close(*args, **kwargs)

    monkeypatch.setattr(plt, "close", spy_close)
    BasicConnectivityPlotsTask.network_in_2D_circular_plot(
        plot_formats=("png",),
        dpi=50,
        size=conn.matrix.shape,
        n_max_2d_plot=10_000,
        conn=conn,
        dir_path=tmp_path,
    )
    return captured.get("axes", [])


def _circular_overview_labels_and_empty(conn, tmp_path, monkeypatch):
    """Return (sorted legend labels, indices of visible-but-empty axes)."""
    axes = _circular_overview_axes(conn, tmp_path, monkeypatch)
    legend_labels = sorted(label for _, _, texts in axes for label in texts)
    visible_empty = [
        i for i, (axison, has_content, _) in enumerate(axes) if axison and not has_content
    ]
    return legend_labels, visible_empty


@pytest.mark.parametrize(
    ("matrix_name", "expected_labels"),
    [
        ("N_10__top_rc_nodes_dim2_rc", ["EXC"]),
        ("N_10__top_nodes_dim6", ["EXC", "INH"]),
    ],
)
def test_circular_overview_single_class_legend(matrix_name, expected_labels, tmp_path, monkeypatch):
    # Regression guard: the circular overview image shares the plot_smallMC legend
    # construction. With a single synapse class it used to leave an empty, still-visible
    # legend axis where the second class marker would go.
    conn = ConnectivityMatrix.from_h5(str(MATRIX_DIR / matrix_name / "connectivity_matrix.h5"))
    assert sorted(conn.vertices["synapse_class"].unique()) == expected_labels

    legend_labels, visible_empty = _circular_overview_labels_and_empty(conn, tmp_path, monkeypatch)

    assert legend_labels == expected_labels
    # The single-class bug surfaced as a framed-but-empty legend axis.
    assert visible_empty == []
