import obi_one as obi

from tests.utils import CIRCUIT_DIR


def test_folder_compression(tmp_path):
    # Set up circuit folder compression
    folder_list = [
        obi.NamedPath(
            name="N_10__top_nodes_dim6",
            path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6"),
        ),
        obi.NamedPath(
            name="N_10__top_rc_nodes_dim2_rc",
            path=str(CIRCUIT_DIR / "N_10__top_rc_nodes_dim2_rc"),
        ),
    ]
    compression_init = obi.FolderCompressionScanConfig.Initialize(
        folder_path=folder_list, file_format=["gz", "bz2", "xz"], file_name="circuit"
    )
    folder_compressions_form = obi.FolderCompressionScanConfig(initialize=compression_init)

    # Run circuit folder compression
    grid_scan = obi.GridScanGenerationTask(
        form=folder_compressions_form,
        output_root=tmp_path / "grid_scan",
        coordinate_directory_option="VALUE",
    )
    grid_scan.execute()
    obi.run_tasks_for_generated_scan(grid_scan)

    # Check that expected files have been created
    instances = grid_scan.single_configs
    assert len(instances) == 6
    for instance in instances:
        fmt = instance.initialize.file_format
        out_path = tmp_path / grid_scan.output_root / instance.initialize.folder_path.name / fmt
        assert (out_path / f"{instance.initialize.file_name}.{fmt}").exists()
