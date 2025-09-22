import obi_one as obi

from tests.utils import DATA_DIR, MATRIX_DIR


def test_basic_connectivity_plots(tmp_path):
    # Set up connectivity plotting
    matrix_list = [
        obi.NamedPath(
            name="N_10__top_nodes_dim6",
            path=str(MATRIX_DIR / "N_10__top_nodes_dim6" / "connectivity_matrix.h5"),
        ),
        obi.NamedPath(
            name="N_10__top_rc_nodes_dim2_rc",
            path=str(MATRIX_DIR / "N_10__top_rc_nodes_dim2_rc" / "connectivity_matrix.h5"),
        ),
    ]

    plot_init = obi.BasicConnectivityPlots.Initialize(
        matrix_path=matrix_list,
        plot_formats=("png", "pdf", "svg"),
        rendering_cmap="custom",
        rendering_color_file=str(DATA_DIR / "colors_tab10.csv"),
    )
    basic_connectivity_plots_form = obi.BasicConnectivityPlots(initialize=plot_init)

    # Run plot generation
    grid_scan = obi.GridScan(
        form=basic_connectivity_plots_form,
        output_root=tmp_path / "grid_scan",
        coordinate_directory_option="VALUE",
    )
    grid_scan.execute(processing_method="run")

    # Check that expected files have been created
    instances = grid_scan.coordinate_instances()
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
